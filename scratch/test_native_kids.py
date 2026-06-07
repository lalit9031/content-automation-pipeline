import asyncio
import edge_tts
from pathlib import Path

async def main():
    out_dir = Path("scratch/native_kids_test")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    text = "Look look! A friendly robot is here! It is holding my hand and helping me win the career race! Yay!"
    boy_text = "Wow! See that big shiny computer? The robot is typing so fast! Zoom zoom! We are running very fast!"
    
    # 1. Test Ana (Native Girl Child Voice)
    path_ana = out_dir / "native_girl_ana.mp3"
    print(f"Generating voice='en-US-AnaNeural' -> {path_ana}")
    try:
        communicate = edge_tts.Communicate(text, "en-US-AnaNeural")
        await communicate.save(str(path_ana))
        print(f"  Success! Size = {path_ana.stat().st_size} bytes")
    except Exception as e:
        print(f"  Error: {e}")
        
    # 2. Test Eric (Native Boy Child Voice)
    path_eric = out_dir / "native_boy_eric.mp3"
    print(f"Generating voice='en-US-EricNeural' -> {path_eric}")
    try:
        communicate = edge_tts.Communicate(boy_text, "en-US-EricNeural")
        await communicate.save(str(path_eric))
        print(f"  Success! Size = {path_eric.stat().st_size} bytes")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
