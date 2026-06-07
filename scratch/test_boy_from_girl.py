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
    boy_text = "Wow! See that big shiny computer? The robot is typing so fast! Zoom zoom! We are running very fast!"
    boy_pacing = humanize_child_pacing_punctuation(boy_text)
    
    out_dir = Path("scratch/test_boy_from_girl_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    pitches_to_test = [
        ("-2Hz", "toddler_boy_pitch_minus2.mp3"),
        ("-3Hz", "toddler_boy_pitch_minus3.mp3"),
        ("-4Hz", "toddler_boy_pitch_minus4.mp3"),
        ("-5Hz", "toddler_boy_pitch_minus5.mp3"),
    ]
    
    for pitch, filename in pitches_to_test:
        path = out_dir / filename
        print(f"Generating toddler boy from Ana with pitch={pitch} -> {path}")
        try:
            # We use en-US-AnaNeural (native child female) but lower pitch to simulate young boy
            communicate = edge_tts.Communicate(boy_pacing, "en-US-AnaNeural", rate="+2%", pitch=pitch)
            await communicate.save(str(path))
            print(f"  Success! Size = {path.stat().st_size} bytes")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
