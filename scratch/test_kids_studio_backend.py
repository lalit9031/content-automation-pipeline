import os
import sys
from pathlib import Path

# Add src to python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from content_pipeline.bots.audio import generate_hindi_song_via_native_audio
from content_pipeline.bots.kids_studio_manifest_core import KIDS_STUDIO_MASTER_REGISTRY

def run_tests():
    print("🧪 Starting Kids Studio Backend Integration Tests...")
    
    # 1. Test KIDS_RHYME_MOUSE
    output_mouse = PROJECT_ROOT / "output" / "test_mouse_rhyme.mp3"
    output_mouse.parent.mkdir(parents=True, exist_ok=True)
    if output_mouse.exists():
        try:
            os.remove(output_mouse)
        except Exception:
            pass
        
    print("\n--- 1. Testing KIDS_RHYME_MOUSE profile ---")
    lyrics_mouse = "[verse]\nएक छोटी सी चिड़िया आई, गाना गाती मुस्कुराई।\n[pause]\nचीं चीं चीं चीं करती जाए।"
    generate_hindi_song_via_native_audio(
        lyrics=lyrics_mouse,
        output_path=output_mouse,
        singer_key="KIDS_RHYME_MOUSE",
        mode="Poem/Rhyme"
    )
    
    # Verify file exists
    assert output_mouse.exists(), "❌ Error: test_mouse_rhyme.mp3 was not created!"
    print(f"✅ Created: {output_mouse}")
    
    # 2. Test STORY_FEMALE_KIND
    output_story = PROJECT_ROOT / "output" / "test_female_story.mp3"
    if output_story.exists():
        try:
            os.remove(output_story)
        except Exception:
            pass
        
    print("\n--- 2. Testing STORY_FEMALE_KIND profile ---")
    lyrics_story = "[narrator]\nएक घने जंगल में एक बूढ़ा बरगद का पेड़ था।\n[pause]\nवह बहुत दयालु था।"
    generate_hindi_song_via_native_audio(
        lyrics=lyrics_story,
        output_path=output_story,
        singer_key="STORY_FEMALE_KIND",
        mode="Storytelling"
    )
    
    # Verify file exists
    assert output_story.exists(), "❌ Error: test_female_story.mp3 was not created!"
    print(f"✅ Created: {output_story}")
    
    print("\n🎉 All integration tests passed successfully!")

if __name__ == "__main__":
    run_tests()
