import asyncio
import edge_tts
from pathlib import Path

def humanize_child_pacing_punctuation(text_data):
    """
    Injects realistic toddler breathing pauses using punctuation (ellipses and spaces)
    to mimic how a cute 3-year-old pauses to think or take short breaths.
    """
    processed = text_data.strip()
    processed = processed.replace("! ", "...!  ")
    processed = processed.replace(", ", ", ...  ")
    processed = processed.replace(". ", "...  ")
    processed = processed.replace("? ", "...?  ")
    return processed

async def main():
    girl_text = "Look look! A friendly robot is here! It is holding my hand and helping me win the career race! Yay!"
    boy_text = "Wow! See that big shiny computer? The robot is typing so fast! Zoom zoom! We are running very fast!"
    
    girl_pacing = humanize_child_pacing_punctuation(girl_text)
    boy_pacing = humanize_child_pacing_punctuation(boy_text)
    
    out_dir = Path("scratch/native_toddlers")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Toddler Girl: en-US-AnaNeural with +5% rate for excitement and child pacing
    girl_path = out_dir / "toddler_girl_ana.mp3"
    print(f"Generating toddler girl using Ana -> {girl_path}")
    try:
        communicate = edge_tts.Communicate(girl_pacing, "en-US-AnaNeural", rate="+4%", pitch="+0Hz")
        await communicate.save(str(girl_path))
        print(f"  Success! Size = {girl_path.stat().st_size} bytes")
    except Exception as e:
        print(f"  Error: {e}")
        
    # Toddler Boy: en-US-EricNeural with +2% rate and child pacing
    boy_path = out_dir / "toddler_boy_eric.mp3"
    print(f"Generating toddler boy using Eric -> {boy_path}")
    try:
        communicate = edge_tts.Communicate(boy_pacing, "en-US-EricNeural", rate="+2%", pitch="+0Hz")
        await communicate.save(str(boy_path))
        print(f"  Success! Size = {boy_path.stat().st_size} bytes")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
