import random
import urllib.parse
from pathlib import Path
from dataclasses import replace
from content_pipeline.config import Settings
from content_pipeline.bots.image import image_provider, ImageVariant

def test_gen():
    style = (
        "Style: Premium 3D character illustration with warm, expressive characters, friendly and approachable. "
        "Shapes and curves are beautifully rounded, smooth modern tech surfaces with tactile glassmorphism textures. "
        "Features a human hand giving a high-five to a robotic assistant's hand, showing detailed finger joints and sleek futuristic white casing with cyan glowing elements. "
        "In the background, a sunny modern office workspace with plants, monitors, and fellow developers. "
        "Color Palette: Saturated natural colors, warm volumetric sun rays, soft pastel purple and cyan highlights. "
        "Lighting: Cinematic depth of field, dramatic contrast, highly detailed textures. "
        "Absolutely no large readable text inside the image."
    )
    prompt = style + " A human developer hand and robot hand high-five inside a beautiful bright modern developer office."
    
    settings = replace(Settings.from_environment(), image_provider="openai")
    print(f"Checking OpenAI keys count: {len(settings.openai_api_keys)}")
    
    provider = image_provider(settings)
    variant = ImageVariant("16:9", 2560, 1440, "test_preview_qhd")
    
    print("Generating premium 2K QHD image with OpenAI (DALL-E 3)...")
    try:
        content = provider.create(prompt, variant)
        out_path = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/content-automation-pipeline/test_gemini_qhd.png")
        out_path.write_bytes(content)
        print(f"Saved premium Gemini QHD image to {out_path}, size: {out_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(content))
        print(f"Final verified image format: {img.format}, size: {img.width}x{img.height}")
    except Exception as e:
        print(f"Failed premium Gemini generation: {e}")

if __name__ == "__main__":
    test_gen()
