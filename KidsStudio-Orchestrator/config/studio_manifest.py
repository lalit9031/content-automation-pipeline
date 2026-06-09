KIDS_STUDIO_MASTER_REGISTRY = {
    "KIDS_RHYME_MOUSE": {
        "display_name": "Squeaky Cartoon Mouse (LittleBubbles Style)",
        "base_tts_voice": "hi-IN-SwaraNeural",
        "gemini_voice": "Puck",               # Youthful voice for Gemini TTS
        "pitch_change": 12,                  # High octave cartoon scaling
        "formant_shift": 1.00,
        "index_rate": 0.40,
        "filter_radius": 3,
        "protect": 0.25,
        "rms_mix_rate": 0.25,
        "bg_music_prompt": "upbeat electronic kindergarten dance track, 115 BPM, 4/4 clapping rhythm"
    },
    "STORY_MALE_PREMIUM": {
        "display_name": "Premium Male Narrator (Wise Baritone Style)",
        "base_tts_voice": "hi-IN-MadhurNeural",
        "gemini_voice": "Rasalgethi",          # Authoritative narrator voice for Gemini TTS
        "pitch_change": -2,                  # Drops register into chest resonance
        "formant_shift": 0.96,
        "index_rate": 0.25,
        "filter_radius": 4,
        "protect": 0.50,                     # Protects breath markers from distortion
        "rms_mix_rate": 0.40,
        "bg_music_prompt": "slow atmospheric cinematic storytelling ambient pad, 0 BPM"
    },
    "STORY_FEMALE_KIND": {
        "display_name": "Premium Female Storyteller (Koo Koo TV Style)",
        "base_tts_voice": "hi-IN-SwaraNeural",
        "gemini_voice": "Puck",               # Soft storytelling voice for Gemini TTS
        "pitch_change": 0,                   # Blocks chipmunk scale leakage
        "formant_shift": 0.98,               # Softens treble edge
        "index_rate": 0.35,
        "filter_radius": 3,
        "protect": 0.45,
        "rms_mix_rate": 0.40,
        "bg_music_prompt": "gentle classical acoustic guitar strumming, soft bansuri flute accents"
    }
}
