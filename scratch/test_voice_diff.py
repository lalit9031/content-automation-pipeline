import asyncio
import edge_tts
from pathlib import Path

async def test_voices():
    voices_to_test = [
        ("hi-IN-MadhurNeural", "+0%", "+0Hz", "hindi_madhur_normal.mp3"),
        ("hi-IN-MadhurNeural", "+15%", "+0Hz", "hindi_madhur_fast.mp3"),
        ("hi-IN-MadhurNeural", "-10%", "-5Hz", "hindi_madhur_deep.mp3"),
        ("hi-IN-SwaraNeural", "+0%", "+0Hz", "hindi_swara_normal.mp3"),
        ("en-IN-PrabhatNeural", "+0%", "+0Hz", "english_prabhat_normal.mp3"),
        ("en-IN-NeerjaNeural", "+0%", "+0Hz", "english_neerja_normal.mp3"),
    ]
    
    text = "नमस्ते, यह एक परीक्षण संदेश है यह देखने के लिए कि क्या विभिन्न आवाजें वास्तव में भिन्न हैं।"
    en_text = "Hello, this is a test message to verify if different voices actually sound different."
    
    out_dir = Path("scratch/voice_test_outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    for voice, rate, pitch, filename in voices_to_test:
        t = en_text if voice.startswith("en") else text
        path = out_dir / filename
        print(f"Generating voice={voice}, rate={rate}, pitch={pitch} -> {path}")
        try:
            communicate = edge_tts.Communicate(t, voice, rate=rate, pitch=pitch)
            await communicate.save(str(path))
            size = path.stat().st_size
            print(f"  Success! Size = {size} bytes")
        except Exception as e:
            print(f"  Error generating {voice}: {e}")

if __name__ == "__main__":
    asyncio.run(test_voices())
