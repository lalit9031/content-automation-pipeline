import urllib.parse
import requests
import random
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
    
    # We will test two cases with different models and seeds to bypass any cache
    test_cases = {
        "flux_seed_1": f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=flux&seed={random.randint(1000, 99999)}",
        "flux_seed_2": f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=flux&seed={random.randint(1000, 99999)}",
        "sana_seed": f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=sana&seed={random.randint(1000, 99999)}",
    }
    
    for name, url in test_cases.items():
        print(f"Testing '{name}': {url[:100]}...")
        try:
            r = requests.get(url, timeout=60)
            print(f"Status for '{name}': {r.status_code}")
            if r.status_code == 200:
                out_path = Path(f"/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/test_seed_{name}.png")
                out_path.write_bytes(r.content)
                print(f"Saved to {out_path}, size: {out_path.stat().st_size / 1024:.1f} KB")
        except Exception as e:
            print(f"Failed for '{name}': {e}")

if __name__ == "__main__":
    test_gen()
