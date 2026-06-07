import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from content_pipeline.bots.audio import generate_hindi_song_via_native_audio

def main():
    lyrics = """
    जय हनुमान ज्ञान गुन सागर। जय कपीस तिहुं लोक उजागर॥
    राम दूत अतुलित बल धामा। अंजनि पुत्र पवनसुत नामा॥
    """
    output_path = Path(__file__).resolve().parent / "test_hindi_song_native.mp3"
    print("🤖 Generating Hindi song using unified native audio router...")
    
    res = generate_hindi_song_via_native_audio(
        lyrics=lyrics,
        output_path=output_path,
        singer_gender="Male",
        selected_ref="None (Text-only)"
    )
    
    print(f"✅ Unified native audio routing test completed! Result path: {res}")
    if res.exists():
        print(f"🔥 Success! Output file size: {res.stat().st_size} bytes")
    else:
        print("❌ Error: Output file was not generated.")

if __name__ == "__main__":
    main()
