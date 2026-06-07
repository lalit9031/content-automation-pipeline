import os
import sys
import time
from pathlib import Path

# Load settings and env manually
PROJECT_ROOT = Path(__file__).resolve().parents[1]
env_path = PROJECT_ROOT / ".env"

if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            os.environ[key.strip()] = val.strip().strip('"').strip("'")

gemini_key = os.getenv("GEMINI_API_KEY")
gemini_model = os.getenv("GEMINI_VIDEO_MODEL", "veo-3.0-fast-generate-001")

if not gemini_key:
    print("Error: GEMINI_API_KEY is not defined in .env!")
    sys.exit(1)

print(f"Initializing Gemini Video Generation...")
print(f"Model: {gemini_model}")
print(f"Key loaded: {gemini_key[:10]}...")

try:
    from google import genai
except ImportError as exc:
    print("google-genai SDK not found! Let's try to install it or use standard google-generativeai.")
    sys.exit(1)

async def generate_video():
    client = genai.Client(api_key=gemini_key)
    prompt = "A high-quality cinematic video of a cute 3-year-old toddler baby laughing and playing happily on a green garden lawn with a fluffy golden retriever puppy dog. Volumetric natural sunlight, smooth dynamic camera motion."
    
    print(f"\nSending video generation request to Gemini Veo...")
    print(f"Prompt: {prompt}")
    
    try:
        operation = client.models.generate_videos(
            model=gemini_model,
            prompt=prompt,
        )
    except Exception as e:
        print(f"Failed to start video generation operation: {e}")
        return

    print("Operation started successfully. Polling for completion...")
    
    poll_count = 0
    while not getattr(operation, "done", False):
        poll_count += 1
        print(f"  Polling attempt {poll_count} (waiting 10 seconds)...")
        time.sleep(10)
        try:
            operation = client.operations.get(operation)
        except Exception as e:
            print(f"  Error polling operation status: {e}")
            break
            
    print("Operation completed!")
    
    response = getattr(operation, "response", None)
    if response is None:
        print("Error: Operation completed without response.")
        return
        
    videos = getattr(response, "generated_videos", None) or []
    if not videos:
        print("Error: No videos found in the response.")
        return
        
    video_file = getattr(videos[0], "video", videos[0])
    
    out_path = Path("scratch/baby_playing_with_dog.mp4")
    print(f"Downloading video bytes...")
    
    try:
        uri = getattr(video_file, "uri", None)
        if uri and hasattr(client.files, "download"):
            downloaded = client.files.download(file=video_file)
            if isinstance(downloaded, bytes):
                out_path.write_bytes(downloaded)
            elif hasattr(downloaded, "read"):
                out_path.write_bytes(downloaded.read())
            else:
                out_path.write_bytes(downloaded)
        else:
            data = getattr(video_file, "video_bytes", None) or getattr(video_file, "data", None)
            if data:
                out_path.write_bytes(data)
            else:
                raise RuntimeError("No direct data bytes found.")
        print(f"🎉 Success! Video saved to {out_path} (Size: {out_path.stat().st_size} bytes)")
    except Exception as e:
        print(f"Failed to download/save video bytes: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(generate_video())
