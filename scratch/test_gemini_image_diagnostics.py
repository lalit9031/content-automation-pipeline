import os
import sys
from pathlib import Path

# Add src/ to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from content_pipeline.config import Settings
from content_pipeline.bots.image import GeminiImageProvider, ImageVariant

def run_diagnostics():
    print("--- Running Gemini Diagnostics ---")
    settings = Settings.from_environment(PROJECT_ROOT)
    print(f"Loaded Settings:")
    print(f"  IMAGE_PROVIDER: {settings.image_provider}")
    print(f"  IMAGEN_MODEL: {settings.imagen_model}")
    print(f"  GEMINI_API_KEY (len): {len(settings.gemini_api_key) if settings.gemini_api_key else 0}")
    print(f"  GEMINI_API_KEYS pool size: {len(settings.gemini_api_keys)}")
    
    # Print keys prefixes to see formats
    if settings.gemini_api_key:
        print(f"  GEMINI_API_KEY prefix: {settings.gemini_api_key[:10]}...")
    for idx, key in enumerate(settings.gemini_api_keys, start=1):
        print(f"  Pool Key {idx} prefix: {key[:10]}...")

    # Instantiate GeminiImageProvider
    try:
        provider = GeminiImageProvider(settings)
        # Force model to imagen-4.0-generate-001 to verify it is supported!
        provider.model = "imagen-4.0-generate-001"
        print(f"Successfully initialized GeminiImageProvider.")
        print(f"  Enforced Model: {provider.model}")
        print(f"  Limiter key count: {provider.limiter.daily_budget if provider.limiter else 'N/A'}")
    except Exception as e:
        print(f"FAILED to initialize GeminiImageProvider: {e}")
        return

    # Try to generate a preview image
    variant = ImageVariant("16:9", 2560, 1440, "test_preview")
    prompt = "A high-detail 3D Pixar claymation illustration of a friendly software developer."
    
    print("\nAttempting to generate image using GeminiImageProvider...")
    try:
        # We temporarily patch or override ensure_capacity or bypass the silent fallback
        # by calling models.generate_images directly on the genai client to see the raw traceback!
        from google import genai
        from google.genai.types import GenerateImagesConfig
        
        for idx, client in enumerate(provider.clients, start=1):
            key_used = settings.gemini_api_keys[idx-1] if idx-1 < len(settings.gemini_api_keys) else settings.gemini_api_key
            print(f"\n--- Testing Client {idx} (Key prefix: {key_used[:10]}...) ---")
            try:
                config = GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio=variant.aspect_ratio,
                    output_mime_type="image/png",
                )
                print(f"Calling client.models.generate_images with model={provider.model}...")
                response = client.models.generate_images(
                    model=provider.model,
                    prompt=prompt,
                    config=config,
                )
                print(f"Response received successfully!")
                from content_pipeline.bots.image import _response_image_bytes
                image_bytes = _response_image_bytes(response)
                if image_bytes:
                    print(f"Image generated! Bytes size: {len(image_bytes)} bytes")
                    out_path = PROJECT_ROOT / f"scratch/diagnosed_gemini_{idx}.png"
                    out_path.write_bytes(image_bytes)
                    print(f"Saved generated image to {out_path}")
                else:
                    print("Response did not contain valid image bytes.")
            except Exception as exc:
                print(f"Client {idx} failed with error:")
                import traceback
                traceback.print_exc()
    except Exception as e:
        print(f"General failure: {e}")

    # Test Pollinations/free-ai provider
    print("\n--- Testing Pollinations/free-ai ImageProvider ---")
    try:
        from content_pipeline.bots.image import PollinationsImageProvider
        pollinations_provider = PollinationsImageProvider(settings)
        print("Initialized PollinationsImageProvider. Attempting generation...")
        img_bytes = pollinations_provider.create(prompt, variant)
        if img_bytes:
            print(f"Success! Pollinations generated image of size: {len(img_bytes)} bytes")
            out_path = PROJECT_ROOT / "scratch/diagnosed_pollinations.png"
            out_path.write_bytes(img_bytes)
            print(f"Saved generated image to {out_path}")
        else:
            print("Pollinations failed to return bytes.")
    except Exception as e:
        print(f"Pollinations provider failed: {e}")

if __name__ == "__main__":
    run_diagnostics()
