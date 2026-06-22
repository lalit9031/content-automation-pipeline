import sys
from pathlib import Path

# Add src folder to PYTHONPATH programmatically
src_dir = Path(__file__).resolve().parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from content_pipeline.config import Settings
from content_pipeline.bots.image import ComfyUIImageProvider, ImageVariant


def main():
    print("Loading settings from .env file...")
    settings = Settings.from_environment()
    
    print(f"ComfyUI URL configured: {settings.comfyui_url}")
    print(f"Image workflow path: {settings.comfyui_image_workflow}")
    
    provider = ComfyUIImageProvider(settings)
    variant = ImageVariant("1:1", 1080, 1080, "test_image")
    
    prompt = (
        "A majestic lion sitting on a golden throne in a royal castle, "
        "fantasy digital art, 8k resolution, cinematic lighting, highly detailed"
    )
    print(f"Generating image with prompt: '{prompt}'...")
    
    try:
        img_bytes = provider.create(prompt, variant)
        
        # Save output
        output_path = Path("test_comfyui_output.png")
        output_path.write_bytes(img_bytes)
        print("\n" + "="*50)
        print(f"SUCCESS! Image successfully generated and saved to:")
        print(f"  {output_path.resolve()}")
        print("="*50)
    except Exception as exc:
        print("\n" + "="*50)
        print(f"ERROR: Generation failed!")
        print(f"Details: {exc}")
        print("="*50)
        print("Please check that:")
        print("1. Your ComfyUI server is running at http://127.0.0.1:8188")
        print(f"2. Your workflow file exists at {settings.comfyui_image_workflow}")
        print(f"3. Your ComfyUI has loaded the model '{settings.comfyui_model_name}'")


if __name__ == "__main__":
    main()
