import os
import math
import sys
import json
from pathlib import Path
from PIL import Image
from google import genai
from google.genai import types

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from orchestrate_production import load_dotenv

def get_gemini_api_keys() -> list[str]:
    """
    Collects all unique Gemini API keys configured in the environment.
    """
    keys = []
    slots = ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4", "GEMINI_API_KEY_5", "GEMINI_API_KEY_6"]
    for slot in slots:
        val = os.environ.get(slot)
        if val and val.strip() and val not in keys:
            keys.append(val.strip())
    return keys

def remove_background(img: Image.Image, threshold: float = 80) -> Image.Image:
    """
    Removes green-screen/chroma-key or uniform background pixels based on color distance
    and crops the image to its non-transparent bounding box.
    """
    img = img.convert("RGBA")
    width, height = img.size
    
    # Check top-left pixel for background reference
    bg_color = img.getpixel((0, 0))
    bg_r, bg_g, bg_b = bg_color[0], bg_color[1], bg_color[2]
    
    datas = img.getdata()
    newData = []
    
    for item in datas:
        r, g, b, a = item
        # Euclidean distance to top-left pixel
        dist = math.sqrt((r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2)
        
        # Chroma key detection (high green, low red/blue)
        is_green = g > 1.35 * r and g > 1.35 * b and g > 60
        
        # Catch white/very light backgrounds if green fails
        is_white = r > 240 and g > 240 and b > 240
        
        if dist < threshold or is_green or is_white:
            newData.append((0, 0, 0, 0))
        else:
            newData.append(item)
            
    img.putdata(newData)
    
    bbox = img.getbbox()
    if bbox:
        img_cropped = img.crop(bbox)
        print(f"   [Process] Cropped canvas from {width}x{height} to {img_cropped.size}")
        return img_cropped
    return img

def generate_image_gemini(prompt: str, aspect_ratio: str, keys: list[str]) -> bytes:
    """
    Queries Gemini Imagen to generate an image. Pools keys for reliability.
    """
    for idx, key in enumerate(keys):
        try:
            print(f"   [Imagen] Querying Gemini Imagen model using key slot {idx+1}/{len(keys)}...")
            client = genai.Client(api_key=key)
            response = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio=aspect_ratio,
                    output_mime_type="image/png"
                )
            )
            if response.generated_images:
                return response.generated_images[0].image.image_bytes
        except Exception as e:
            print(f"   ⚠️ Key slot {idx+1} failed: {e}")
    return b""

def main():
    load_dotenv()
    keys = get_gemini_api_keys()
    if not keys:
        raise ValueError("❌ No Gemini API keys found in environment variables.")
        
    assets_dir = PROJECT_ROOT / "assets" / "character"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # Prompts for characters and backgrounds
    jobs = [
        {
            "name": "peacock_body",
            "prompt": "A beautiful 2D cartoon peacock, standing facing right, vibrant colorful feathers, kids storybook illustration style, isolated on a bright solid chroma key green background",
            "type": "character",
            "aspect_ratio": "1:1"
        },
        {
            "name": "kalu_body", # Kalu the Crow
            "prompt": "A cute 2D cartoon crow bird, standing facing left, simple black feathers, big curious eye, kids storybook illustration style, isolated on a bright solid chroma key green background",
            "type": "character",
            "aspect_ratio": "1:1"
        },
        {
            "name": "jungle_bg",
            "prompt": "A beautiful 2D cartoon jungle forest background with lush green trees, bright sunny day, flowering bushes, clear blue sky, kids storybook illustration style, 16:9 aspect ratio",
            "type": "background",
            "aspect_ratio": "16:9"
        },
        {
            "name": "hunter_bg",
            "prompt": "A beautiful 2D cartoon jungle forest background with a thick rope net lying on the forest ground, cloudy gloomy sky, kids storybook illustration style, 16:9 aspect ratio",
            "type": "background",
            "aspect_ratio": "16:9"
        }
    ]
    
    print("🚀 Starting AI Asset Generation (Gemini Imagen)...")
    
    for job in jobs:
        name = job["name"]
        prompt = job["prompt"]
        aspect_ratio = job["aspect_ratio"]
        dest_path = assets_dir / f"{name}.png"
        
        print(f"\n🎨 Generating [{name}]...")
        image_bytes = generate_image_gemini(prompt, aspect_ratio, keys)
        
        if not image_bytes:
            print(f"❌ Failed to generate {name}. Check logs.")
            continue
            
        temp_path = assets_dir / f"{name}_temp.png"
        temp_path.write_bytes(image_bytes)
        
        # Process and save
        try:
            img = Image.open(temp_path)
            if job["type"] == "character":
                print(f"✂️ Keying out green background for character [{name}]...")
                processed_img = remove_background(img, threshold=90)
                processed_img.save(dest_path, "PNG")
            else:
                print(f"💾 Saving background [{name}]...")
                img = img.resize((1280, 720), Image.Resampling.LANCZOS)
                img.save(dest_path, "PNG")
            print(f"✨ Successfully saved asset to: {dest_path}")
        except Exception as e:
            print(f"❌ Failed processing {name}: {e}")
        finally:
            if temp_path.exists():
                os.remove(temp_path)
                
    print("\n🎉 Asset Generation and Processing Complete!")

if __name__ == "__main__":
    main()
