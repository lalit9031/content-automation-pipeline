import sys
import logging
from pathlib import Path

# Setup verbose logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Add src folder to PYTHONPATH programmatically
src_dir = Path(__file__).resolve().parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from content_pipeline.config import Settings
from content_pipeline.bots.image import ComfyUIImageProvider, ImageVariant
from content_pipeline.bots.agent_orchestrator import AgentOrchestrator

def main():
    print("Loading settings...")
    settings = Settings.from_environment()
    
    # Force ComfyUI image provider
    provider = ComfyUIImageProvider(settings)
    variant = ImageVariant("1:1", 1080, 1080, "test_qa_image")
    
    # Let's test the Pixar 3D animation style prompt!
    prompt = (
        "A beautiful 3D Disney Pixar style animated illustration of two young Indian boys, Sonu and Monu, "
        "standing together happily as best friends in the center. Sonu has a cheerful smile and neat black hair, "
        "and Monu is laughing warmly next to him. The background is a bright, whimsical, kid-friendly village "
        "with cute colorful cottages, green hills, flying butterflies, a blue sky with fluffy clouds, "
        "and colorful flowers, soft volumetric lighting, detailed clean render, high quality."
    )
    print(f"Generating image with prompt: '{prompt}'...")
    
    # We call the provider.create directly, which triggers the QA audit & repair loop inside ComfyUIImageProvider
    try:
        img_bytes = provider.create(prompt, variant)
        output_path = Path("test_qa_output.png")
        output_path.write_bytes(img_bytes)
        print(f"Generation complete! Saved to {output_path.resolve()}")
    except Exception as exc:
        print(f"Generation failed: {exc}")

if __name__ == "__main__":
    main()
