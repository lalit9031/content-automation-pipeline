import os
import json
import sys
from google import genai
from google.genai import types

def test():
    # Read keys from .env
    from pathlib import Path
    keys = []
    if Path(".env").exists():
        for line in Path(".env").read_text().splitlines():
            if line.startswith("GEMINI_API_KEY"):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    keys.append(val)
    
    if not keys:
        print("No GEMINI_API_KEYs found in .env!")
        sys.exit(1)
        
    print(f"Loaded {len(keys)} Gemini keys from .env.")
    
    prompt = """
    Create a highly engaging 4-scene video script about: "3 AI Tools that will 10x your coding".
    Return a raw JSON object strictly conforming to this schema (just direct raw JSON text):
    {
        "youtube_title": "A highly catchy title",
        "youtube_description": "Description",
        "tags": ["tag1", "tag2"],
        "scenes": [
            {
                "scene_number": 1,
                "narration": "What the voiceover speaks.",
                "screen_text": "Text overlay",
                "visual_prompt": "3D Pixar claymation scene visual prompt"
            }
        ]
    }
    """
    
    for idx, key in enumerate(keys):
        print(f"Trying Gemini Key {idx + 1}...")
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            print(f"✅ Key {idx + 1} Succeeded!")
            print(response.text)
            return
        except Exception as e:
            print(f"❌ Key {idx + 1} Failed: {e}")
            
    print("All keys failed.")


if __name__ == "__main__":
    test()
