import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "src"))

from content_pipeline.bots.audio import generate_hindi_song_via_native_audio

def main():
    print("🚀 Starting test for Hindi Kids Poem/Rhyme Mode...")
    
    lyrics = (
        "[chorus]\n"
        "क से कबूतर, ख से खरगोश!\n"
        "ग से गमला, घ से घर!\n"
        "[verse]\n"
        "आओ मिलकर सीखें अक्षर!\n"
        "प्यारे-प्यारे हिंदी के स्वर!"
    )
    
    output_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio")
    output_path = output_dir / "LittleBubbles_Rhyme_Final.mp3"
    
    print(f"Generating audio in Poem/Rhyme mode at: {output_path}")
    
    # Run with hi_kids_ananya (mapped to shreya_ghoshal)
    res = generate_hindi_song_via_native_audio(
        lyrics=lyrics,
        output_path=output_path,
        singer_gender="Female",
        selected_ref="None (Text-only)",
        singer_key="hi_kids_ananya",
        mode="Poem/Rhyme"
    )
    
    print(f"🎉 Success! Audio generated successfully at: {res}")

if __name__ == "__main__":
    main()
