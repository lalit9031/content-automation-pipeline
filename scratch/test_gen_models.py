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
    
    # We will test multiple models: 'flux', 'gptimage-large', 'nova-canvas', 'klein'
    models = ['flux', 'gptimage-large', 'klein', 'nova-canvas']
    
    encoded = urllib.parse.quote(prompt)
    for model in models:
        # According to documentation, gen.pollinations.ai uses:
        # https://gen.pollinations.ai/image/{prompt}?model={model}&width=1280&height=720
        url = f"https://gen.pollinations.ai/image/{encoded}?model={model}&width=1280&height=720&enhance=false"
        print(f"Querying model '{model}': {url[:100]}...")
        try:
            r = requests.get(url, timeout=60)
            print(f"Status for '{model}': {r.status_code}")
            if r.status_code == 200:
                out_path = Path(f"/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/test_model_{model}.png")
                out_path.write_bytes(r.content)
                print(f"Saved '{model}' to {out_path}, size: {out_path.stat().st_size / 1024:.1f} KB")
        except Exception as e:
            print(f"Failed for '{model}': {e}")

if __name__ == "__main__":
    test_gen()
