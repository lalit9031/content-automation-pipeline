import asyncio
import edge_tts
from pathlib import Path

def inject_dramatic_story_pauses_punctuation(text_data):
    """
    Translates dramatic storytelling XML pauses into natural punctuation pacing
    (ellipses, commas, and extra spaces) to safely bypass Microsoft's tag block.
    """
    processed = text_data.strip()
    # Inject a warm, breathing 350ms-like pause at commas
    processed = processed.replace(", ", ", ...  ")
    processed = processed.replace(",", ", ...  ")
    
    # Inject a long, dramatic 750ms-like suspense hold at periods
    processed = processed.replace(". ", ". ...   ")
    processed = processed.replace(".", ". ...   ")
    
    # Inject a questioning suspense pause
    processed = processed.replace("? ", "? ...   ")
    processed = processed.replace("?", "? ...   ")
    return processed

async def main():
    story_script = (
        "Once upon a time, in a world moving faster than light, a young fresher stood at the edge of a massive career race. "
        "The stadium was filled with heavy competition, and the old corporate walls looked impossibly tall."
    )
    
    story_pacing = inject_dramatic_story_pauses_punctuation(story_script)
    
    out_dir = Path("scratch/storyteller_punctuation")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Soothing Female Storyteller (Warm & Patient)
    female_path = out_dir / "story_female_narration.mp3"
    print(f"Generating female storyteller voice -> {female_path}")
    try:
        communicate = edge_tts.Communicate(story_pacing, "en-IN-NeerjaNeural", rate="-12%", pitch="-2Hz")
        await communicate.save(str(female_path))
        print(f"  Success! Size = {female_path.stat().st_size} bytes")
    except Exception as e:
        print(f"  Error: {e}")
        
    # Deep Charismatic Male Storyteller (Calm & Authoritative)
    male_path = out_dir / "story_male_narration.mp3"
    print(f"Generating male storyteller voice -> {male_path}")
    try:
        communicate = edge_tts.Communicate(story_pacing, "en-IN-PrabhatNeural", rate="-15%", pitch="-4Hz")
        await communicate.save(str(male_path))
        print(f"  Success! Size = {male_path.stat().st_size} bytes")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
