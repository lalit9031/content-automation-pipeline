import sys
import os
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from content_pipeline.config import Settings

# Import local function or replica of it to catch exceptions
def test_expansion():
    settings = Settings.from_environment(Path(__file__).resolve().parent.parent)
    prompt = "Create a happy upbeat song about coding at night"
    singer_gender = "Male"
    language = "Hindi"
    
    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]
    if os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") not in keys:
        keys.insert(0, os.environ.get("GEMINI_API_KEY"))
    keys = [k for k in keys if k]
    
    print("Keys found in test:", len(keys))
    for i, key in enumerate(keys):
        print(f"Trying key index {i} (starts with {key[:10]}...):")
        system_instruction = (
            "You are a music composer and lyricist. Expand the user's idea into complete lyrics and style description. "
            "The output must be JSON with keys 'lyrics' and 'style'."
        )
        user_prompt = f"""
        User Song Idea: "{prompt}"
        Singer Voice Gender Selection: "{singer_gender}"
        Target Song Language: "{language}"
        
        Requirements:
        1. If the Target Song Language is 'Hindi', write the lyrics in standard Devanagari script (Hindi characters) like 'जय हनुमान ज्ञान गुन सागर' rather than Romanized/Hinglish (e.g. 'Jai Hanuman'). This forces the neural network to activate its native Indian mouth-shape and dental consonant engines for a perfect native accent. Explicitly mention 'native Indian {singer_gender.lower()} singing voice with natural Indian accent', 'Bollywood style playback singer (e.g. Arijit Singh/Atif Aslam style male, Shreya Ghoshal style female)', 'expressive emotional delivery with traditional vocal ornamentations (gamaq and murki)', 'clear native pronunciation', 'traditional Indian instruments (sitar, bansuri flute, dholak, tabla, acoustic guitar)', and 'highly polished T-Series/Saregama style commercial pop mix with grand cinematic reverb and spacious stereo delay' in the style description.
        2. SPECIAL DEVOTIONAL EXCEPTION: If the User Song Idea or prompt contains references to Hindu deities, devotional topics, or prayers (such as 'Hanuman', 'Chalisa', 'bhajan', 'aarti', 'spiritual', 'ram', 'krishna', 'shiva', 'ganesha', 'temple', 'prayer', 'devotional'), then override the modern commercial pop styles. Instead, explicitly require:
           - 'authentic traditional Indian devotional bhajan/kirtan mood'
           - 'deeply spiritual native Indian {singer_gender.lower()} devotional singer voice'
           - 'traditional acoustic instrumentation: bansuri flute, harmonium, sitar, dholak, tabla, manjira hand cymbals'
           - 'peaceful and prayerful tempo (65-75 BPM)'
           - 'strictly no modern electronic dance drums, no heavy synthesizers, no modern EDM elements'
           - 'sacred temple hall acoustics with warm ambient reverb'
        3. If the Target Song Language is 'English', write the lyrics in English.
        4. Structure the lyrics with standard tags like [verse] and [chorus]. Avoid [intro] or [outro] tags. Keep it to 2-3 short verses and 1-2 choruses.
        5. The 'style' string must be a comma-separated description of instruments, tempo (BPM), vocal qualities, and musical genre. Make it match the song idea.
        
        Return a raw JSON object matching this schema:
        {{
            "lyrics": "verse and chorus text",
            "style": "comma-separated musical style description"
        }}
        """
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    system_instruction=system_instruction
                )
            )
            print("Response text received:", response.text)
            data = json.loads(response.text)
            print("Successfully parsed JSON!")
            print("Lyrics:\n", data.get("lyrics")[:100], "...")
            print("Style:\n", data.get("style"))
            break
        except Exception as e:
            print("FAILED with exception:", type(e), e)
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_expansion()
