import asyncio
import edge_tts
from pathlib import Path

class SSMLCommunicate(edge_tts.Communicate):
    def __init__(self, text, voice, **kwargs):
        super().__init__(text, voice, **kwargs)
        from edge_tts.communicate import split_text_by_byte_length, remove_incompatible_characters
        self.texts = split_text_by_byte_length(
            remove_incompatible_characters(text),
            4096,
        )

async def test_variations():
    voice = "hi-IN-SwaraNeural"
    
    # Test 1: Plain text with bypass active (to check if bypass is stable)
    text_plain = "Look look! A friendly robot is here! It is holding my hand."
    out_1 = Path("scratch/test_plain_bypass.mp3")
    
    # Test 2: Standard break format
    text_break = 'Look look! <break time="1s"/> A friendly robot is here!'
    out_2 = Path("scratch/test_break_bypass.mp3")
    
    # Test 3: Simple break format (no time argument, just empty break)
    text_simple_break = 'Look look! <break/> A friendly robot is here!'
    out_3 = Path("scratch/test_simple_break_bypass.mp3")

    for idx, (t, path, desc) in enumerate([
        (text_plain, out_1, "Bypass plain text"),
        (text_break, out_2, "Standard break <break time='1s'/>"),
        (text_simple_break, out_3, "Simple break <break/>")
    ], 1):
        print(f"\nRunning Test {idx}: {desc}...")
        try:
            communicate = SSMLCommunicate(t, voice, rate="+20%", pitch="+11Hz")
            await communicate.save(str(path))
            print(f"  Success! File size = {path.stat().st_size} bytes")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_variations())
