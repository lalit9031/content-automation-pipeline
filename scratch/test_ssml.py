import asyncio
import edge_tts
from pathlib import Path

async def test_ssml():
    voice = "en-IN-PrabhatNeural"
    text = (
        "Good morning, and welcome to this comprehensive industry analysis. "
        "Today, we are examining a critical market paradigm shift: "
        "How the next generation of freshers is leveraging artificial intelligence."
    )
    
    ssml_payload = f"""
    <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>
        <voice name='{voice}'>
            <prosody rate='-6%' pitch='-4Hz'>
                {text}
            </prosody>
        </voice>
    </speak>
    """
    
    out_path = Path("scratch/test_ssml_output.mp3")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    print("Generating SSML audio...")
    try:
        communicate = edge_tts.Communicate(ssml_payload, voice, is_ssml=True)
        await communicate.save(str(out_path))
        print(f"Success! Generated file size = {out_path.stat().st_size} bytes")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_ssml())
