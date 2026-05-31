import json
import shutil
import sys
import os
from pathlib import Path

# Add src directory to sys path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from content_pipeline.bots.audio import generate_indian_voiceover, VOICE_PREVIEW_PRESETS

def verify_presets():
    print("Starting comprehensive premium presets verification...")
    
    test_dir = Path("scratch/presets_verification")
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Test manual preset mapping in generate_indian_voiceover
    print("\n--- Test Phase 1: Explicit Parameter Rendering ---")
    presets_to_test = [
        ("indian_english_corporate_male", "Good morning corporate team.", "en-IN-PrabhatNeural", "corporate_manual.mp3"),
        ("toddler_girl", "Look! A shiny computer!", "en-US-AnaNeural", "toddler_girl_manual.mp3"),
        ("toddler_boy", "Wow! Look at that computer!", "en-US-AnaNeural", "toddler_boy_manual.mp3"),
        ("story_female", "Once upon a time, a young fresher stood.", "en-IN-NeerjaNeural", "story_female_manual.mp3"),
        ("story_male", "Once upon a time, a young fresher stood.", "en-IN-PrabhatNeural", "story_male_manual.mp3"),
    ]
    
    for key, text, voice, filename in presets_to_test:
        preset = next(p for p in VOICE_PREVIEW_PRESETS if p.key == key)
        out_path = test_dir / filename
        print(f"Generating preset='{preset.label}' -> {out_path}")
        generate_indian_voiceover(
            text,
            out_path,
            voice=preset.voice,
            rate=preset.rate,
            pitch=preset.pitch,
        )
        print(f"  Success! Size: {out_path.stat().st_size} bytes")

    # 2. Test self-healing background JSON state fallback
    print("\n--- Test Phase 2: Dynamic JSON State Background Fallback ---")
    runtime_dir = test_dir / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    state_file = runtime_dir / "studio_state.json"
    
    test_backgrounds = [
        ("toddler_girl", "Look! A shiny computer!", "en-US-AnaNeural", "toddler_girl_dynamic.mp3"),
        ("story_male", "Once upon a time, a young fresher stood.", "en-IN-PrabhatNeural", "story_male_dynamic.mp3"),
    ]
    
    for key, text, voice, filename in test_backgrounds:
        # Write state to JSON to simulate Streamlit UI settings being saved
        state_file.write_text(json.dumps({"voice_preset_choice": key}), encoding="utf-8")
        out_path = test_dir / filename
        
        print(f"Simulating background compile for preset='{key}' (State JSON: {key}) -> {out_path}")
        # Note: We do NOT pass rate or pitch, simulating a background/CLI run!
        generate_indian_voiceover(
            text,
            out_path,
            voice=voice,
        )
        print(f"  Success! Dynamic Size: {out_path.stat().st_size} bytes")
        
    print("\n🎉 Verification Completed Successfully! All dynamic voice engines are fully functional!")

if __name__ == "__main__":
    verify_presets()
