import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from content_pipeline.config import Settings
from content_pipeline.bots.audio import generate_hindi_song_via_native_audio

def main():
    settings = Settings.from_environment()
    lyrics = (
        "[pause] एक समय की बात है, एक जंगल में एक बहुत ही बुद्धिमान कछुआ रहता था। "
        "[pause] उसी जंगल में एक खरगोश भी रहता था, जिसे अपनी गति पर बहुत घमंड था। "
        "[pause] एक दिन दोनों ने दौड़ लगाने का फैसला किया। "
        "[pause] खरगोश तेजी से भागा और आधा रास्ता तय करके सो गया। "
        "[pause] कछुआ धीरे-धीरे बिना रुके चलता रहा और अंत में दौड़ जीत गया। "
        "[pause] इस कहानी से हमें सीख मिलती है कि धीरे और लगातार चलने वाले ही हमेशा जीतते हैं।"
    )
    output_path = Path(__file__).resolve().parent / "test_hindi_song_native.mp3"
    print("🤖 Generating Hindi storytelling audio using unified native audio router...")
    
    res = generate_hindi_song_via_native_audio(
        lyrics=lyrics,
        output_path=output_path,
        singer_gender="Female",
        selected_ref="None (Text-only)",
        hf_token=settings.hf_token,
        singer_key="STORY_FEMALE_KIND",
        mode="Storytelling"
    )
    
    print(f"✅ Unified native audio routing test completed! Result path: {res}")
    if res.exists():
        print(f"🔥 Success! Output file size: {res.stat().st_size} bytes")
    else:
        print("❌ Error: Output file was not generated.")

if __name__ == "__main__":
    main()
