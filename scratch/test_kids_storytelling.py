import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from content_pipeline.bots.audio import generate_hindi_song_via_native_audio

def main():
    print("🚀 Starting test for Hindi Kids Storytelling Mode...")
    
    lyrics = (
        "[pause] एक समय की बात है, एक जंगल में एक बहुत ही बुद्धिमान कछुआ रहता था। "
        "[pause] उसी जंगल में एक खरगोश भी रहता था, जिसे अपनी गति पर बहुत घमंड था। "
        "[pause] एक दिन दोनों ने दौड़ लगाने का फैसला किया। "
        "[pause] खरगोश तेजी से भागा और आधा रास्ता तय करके सो गया। "
        "[pause] कछुआ धीरे-धीरे बिना रुके चलता रहा और अंत में दौड़ जीत गया। "
        "[pause] इस कहानी से हमें सीख मिलती है कि धीरे और लगातार चलने वाले ही हमेशा जीतते हैं।"
    )
    
    output_dir = Path("/Users/lalitprasadsingh/Desktop/antigravity/New Audio")
    output_path = output_dir / "LittleBubbles_Story_Final.mp3"
    
    print(f"Generating audio in Storytelling mode at: {output_path}")
    
    # Let's run with hi_kids_ananya vocal profile
    res = generate_hindi_song_via_native_audio(
        lyrics=lyrics,
        output_path=output_path,
        singer_gender="Female",
        selected_ref="None (Text-only)",
        singer_key="hi_kids_ananya",
        mode="Storytelling"
    )
    
    print(f"🎉 Success! Audio generated successfully at: {res}")

if __name__ == "__main__":
    main()
