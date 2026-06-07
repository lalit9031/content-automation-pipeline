import os
import sys
from pathlib import Path
from google import genai

sys.path.append(str(Path(__file__).parent.parent / "src"))
from content_pipeline.config import Settings

def list_gemini_models():
    settings = Settings.from_environment()
    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    
    keys = [k for k in keys if k]
    if not keys:
        print("No GEMINI_API_KEY found!")
        sys.exit(1)
        
    key = keys[1] if len(keys) > 1 else keys[0] # use Key 2 since Key 1 failed auth
    print(f"Using key ending with: {key[-6:] if len(key) > 6 else key}")
    
    client = genai.Client(api_key=key)
    print("Listing models:")
    try:
        for m in client.models.list():
            print(f"{m.name} -> {m.supported_actions}")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    list_models = list_gemini_models
    list_models()
