import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from content_pipeline.bots.audio import generate_edge_tts_song_fallback

def main():
    lyrics = """
    जय हनुमान ज्ञान गुन सागर। जय कपीस तिहुं लोक उजागर॥
    राम दूत अतुलित बल धामा। अंजनि पुत्र पवनसुत नामा॥
    """
    output_path = Path(__file__).resolve().parent / "test_edge_fallback_mix.mp3"
    print("🤖 Generating mixed backup song using Edge-TTS + Beat fallback...")
    
    # We pass 'None (Text-only)' so it falls back to desktop New Audio folder beats or ambient generation
    res = generate_edge_tts_song_fallback(
        lyrics=lyrics,
        output_path=output_path,
        singer_gender="Male",
        selected_ref="None (Text-only)"
    )
    
    print(f"✅ Backup generation test completed! Result path: {res}")
    if res.exists():
        print(f"🔥 Success! Output file size: {res.stat().st_size} bytes")
    else:
        print("❌ Error: Output file was not generated.")

if __name__ == "__main__":
    main()
