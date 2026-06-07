import urllib.parse
import requests
import time
from pathlib import Path

def main():
    prompts = {
        34: "3D social media icons Instagram LinkedIn Twitter floating, mesh background, volumetric studio lighting, claymation style, no text",
        35: "3D outro screen endcard, Subscribe button, thumbs up Like icon, golden notification Bell, tech background, no text"
    }
    
    for num, prompt in prompts.items():
        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=576&nologo=true&private=true"
        
        print(f"Generating Scene {num} with short prompt...")
        try:
            time.sleep(3)
            r = requests.get(url, timeout=30)
            print(f"Status: {r.status_code}")
            r.raise_for_status()
            out_path = Path(f"/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/test_{num}.png")
            out_path.write_bytes(r.content)
            print(f"Saved to {out_path}, size: {out_path.stat().st_size / 1024:.1f} KB")
        except Exception as e:
            print(f"Failed for Scene {num}: {e}")

if __name__ == "__main__":
    main()
