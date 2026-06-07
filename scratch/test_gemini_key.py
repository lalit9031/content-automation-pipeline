import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from content_pipeline.config import Settings
from google import genai

def main():
    settings = Settings.from_environment()
    print("API Key Pool:", settings.gemini_api_keys)
    print("First API Key:", settings.gemini_api_key)
    
    key = settings.gemini_api_key
    if not key:
        print("❌ No API key found.")
        return
        
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Write a 1-line poem about rain."
        )
        print("✅ SUCCESS!")
        print("Response:", response.text)
    except Exception as e:
        print("❌ FAILED!")
        print("Error:", e)

if __name__ == "__main__":
    main()
