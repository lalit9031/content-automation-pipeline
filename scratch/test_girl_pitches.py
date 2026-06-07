import asyncio
import edge_tts
from pathlib import Path

def humanize_child_pacing_punctuation(text_data):
    processed = text_data.strip()
    processed = processed.replace("! ", "...!  ")
    processed = processed.replace(", ", ", ...  ")
    processed = processed.replace(". ", "...  ")
    processed = processed.replace("? ", "...?  ")
    return processed

async def main():
    girl_text = "Look look! A friendly robot is here! It is holding my hand and helping me win the career race! Yay!"
    girl_pacing = humanize_child_pacing_punctuation(girl_text)
    
    out_dir = Path("scratch/test_girl_pitches_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    variants = [
        ("+2Hz", "+6%", "girl_pitch_plus2_rate6.mp3"),
        ("+3Hz", "+8%", "girl_pitch_plus3_rate8.mp3"),
        ("+4Hz", "+10%", "girl_pitch_plus4_rate10.mp3"),
        ("+0Hz", "+4%", "girl_pitch_plus0_rate4.mp3"),  # Current settings
    ]
    
    for pitch, rate, filename in variants:
        path = out_dir / filename
        print(f"Generating toddler girl from Ana with pitch={pitch}, rate={rate} -> {path}")
        try:
            communicate = edge_tts.Communicate(girl_pacing, "en-US-AnaNeural", rate=rate, pitch=pitch)
            await communicate.save(str(path))
            print(f"  Success! Size = {path.stat().st_size} bytes")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
