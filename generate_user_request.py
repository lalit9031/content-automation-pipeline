import sys
from pathlib import Path

# Add src folder to PYTHONPATH programmatically
src_dir = Path(__file__).resolve().parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from content_pipeline.config import Settings
from content_pipeline.bots.image import ComfyUIImageProvider, ImageVariant


def main():
    settings = Settings.from_environment()
    
    # Target folders
    base_dir = Path(r"C:\Users\user\Desktop\Output file")
    img_dir = base_dir / "image"
    vid_dir = base_dir / "video"
    aud_dir = base_dir / "audio"
    
    # Create directories
    img_dir.mkdir(parents=True, exist_ok=True)
    vid_dir.mkdir(parents=True, exist_ok=True)
    aud_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Created folders: \n - {img_dir}\n - {vid_dir}\n - {aud_dir}")
    
    provider = ComfyUIImageProvider(settings)
    variant = ImageVariant("1:1", 1080, 1080, "kids_playing_in_park")
    
    prompt = (
        "Refined 3D animated Pixar style medium shot of a cute girl holding a large, proportional colorful umbrella over her head. "
        "She is standing on a grassy path, a little far from the river bank which is clearly visible in the mid-background with gentle ripples on the water under light rain. "
        "She has a perfectly symmetrical face, perfectly aligned and beautiful expressive eyes, and a cheerful smile. "
        "Clean, sharp focus on the girl and umbrella, realistic rain falling, vibrant colors, masterfully rendered."
    )
    print(f"Generating image with prompt: '{prompt}'...")
    
    try:
        # This will try ComfyUI first. Since it's offline, it will fall back to Pollinations (free Flux)
        img_bytes = provider.create(prompt, variant)
        
        output_file = img_dir / f"girl_in_rain_aligned{provider.extension}"
        output_file.write_bytes(img_bytes)
        print(f"SUCCESS! Saved generated image to: {output_file.resolve()}")
    except Exception as e:
        print(f"ERROR during image generation: {e}")


if __name__ == "__main__":
    main()
