import asyncio
import edge_tts
from pathlib import Path

def humanize_child_pacing_punctuation(text_data):
    """
    Injects realistic toddler breathing pauses using punctuation (ellipses and spaces)
    instead of XML break tags, which the service rejects.
    """
    processed = text_data.strip()
    # Replace exclamation marks and periods with ellipses to force natural neural pauses
    processed = processed.replace("! ", "...!  ")
    processed = processed.replace(", ", ", ...  ")
    processed = processed.replace(". ", "...  ")
    return processed

async def main():
    girl_text = "Look look! A friendly robot is here! It is holding my hand and helping me win the career race! Yay!"
    boy_text = "Wow! See that big shiny computer? The robot is typing so fast! Zoom zoom! We are running very fast!"
    
    girl_pacing = humanize_child_pacing_punctuation(girl_text)
    boy_pacing = humanize_child_pacing_punctuation(boy_text)
    
    out_dir = Path("scratch/child_voices_punctuation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 3-4 Year Old Little Girl (Excited & Playful)
    girl_path = out_dir / "toddler_girl_accent.mp3"
    print(f"Generating girl toddler voice -> {girl_path}")
    try:
        communicate = edge_tts.Communicate(girl_pacing, "hi-IN-SwaraNeural", rate="+20%", pitch="+11Hz")
        await communicate.save(str(girl_path))
        print(f"  Success! Size = {girl_path.stat().st_size} bytes")
    except Exception as e:
        print(f"  Error: {e}")
        
    # 3-4 Year Old Little Boy (High-Energy Cartoon)
    boy_path = out_dir / "toddler_boy_accent.mp3"
    print(f"Generating boy toddler voice -> {boy_path}")
    try:
        communicate = edge_tts.Communicate(boy_pacing, "hi-IN-MadhurNeural", rate="+16%", pitch="+8Hz")
        await communicate.save(str(boy_path))
        print(f"  Success! Size = {boy_path.stat().st_size} bytes")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
