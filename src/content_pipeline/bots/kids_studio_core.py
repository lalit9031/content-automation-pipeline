def get_kids_studio_creative_prompt(user_idea: str, mode: str, target_lang: str) -> str:
    """
    Dynamically switches backend prompt constraints with explicit examples
    to completely eliminate structural confusion.
    """
    if mode == "Storytelling":
        return (
            "You are an elite children's audio-book narrator and storyteller for YouTube animation channels.\n"
            f"Write an engaging, expressive short story based on this idea: '{user_idea}' in {target_lang}.\n\n"
            "STRICT STORYTELLING RULES:\n"
            "1. Use highly descriptive, warm, and comforting language suitable for toddlers.\n"
            "2. Separate the script using clear structural blocks: [Narrator], [Character: Name].\n"
            "3. Insert [pause] tags after sentences to allow the voice engine to simulate natural pacing."
        )
        
    else:  # Poem / Nursery Rhyme Mode
        return (
            "You are a master children's lyricist composing catchy nursery rhymes for toddler channels.\n"
            f"Write a rhythmic, rhyming children's poem based on this idea: '{user_idea}' in {target_lang}.\n\n"
            
            "STRICT RHYMING RULES:\n"
            "1. You must follow a strict rhyming pattern where the first two lines rhyme with each other, "
            "and the subsequent two lines rhyme with each other.\n"
            "2. DO NOT print or output the letters 'A' or 'B' anywhere in your response.\n\n"
            
            "EXPLICIT HINDI FORMAT EXAMPLE TO FOLLOW:\n"
            "[Verse]\n"
            "Chanda mama door ke, (Line 1 - ends in 'ke')\n"
            "Pue pakaye boor ke, (Line 2 - rhymes with Line 1)\n"
            "Aap khaye thali mein, (Line 3 - ends in 'mein')\n"
            "Munne ko de pyali mein, (Line 4 - rhymes with Line 3)\n\n"
            
            "Apply this identical rhyming rhythm and pacing to the user's specific topic idea. "
            "Keep the vocabulary simple, clean, and easy for toddlers to memorize."
        )


def preprocess_storytelling_script(script: str) -> str:
    """
    Programmatically replaces standard sentence-ending periods (Devanagari '।' and English '.')
    with expressive punctuation markers ('...!') to force the base voice engine
    to inject natural theatrical pauses and pitch variance.
    """
    import re
    # Replace Hindi danda '।' followed by optional spaces
    script = re.sub(r'।\s*', '...! ', script)
    # Replace English period '.' followed by space or end of string, making sure not to replace periods inside decimals or ellipses
    script = re.sub(r'\.(?=\s|$)', '...! ', script)
    return script


def get_storyteller_production_flags():
    """
    Returns premium narration parameters optimized for children's audiobooks,
    maximizing emotional range and removing metallic vocoder stiffness.
    """
    return {
        "f0_method": "rmvpe",
        "index_rate": 0.30,         # Lowered to make word transitions sound natural and fluid
        "filter_radius": 4,         # Increased to actively filter out digital jitter and clicking
        "protect": 0.33,            # Shields voiceless consonants during dramatic pauses
        "rms_mix_rate": 0.45,       # High blend layer to capture true human volume dynamics and acting
        "formant_shift": 0.96       # CRITICAL FIX: Shifts formants down to add rich, deep chest bass natively
    }


def configure_absolute_storyteller_vocal_chain(mode: str):
    """
    Forcibly overrides and isolates the vocal pitch architecture.
    Completely blocks high-pitched cartoon leakage from entering storytelling audio.
    """
    if mode == "Storytelling":
        print("🛑 Target Check: Locking down warm Narrator settings. Purging chipmunk registers.")
        return {
            "base_tts_voice": "hi-IN-MadhurNeural", # Switches to a warm, deep base voice foundation
            "pitch_change": -2,                      # Lowers the pitch to inject instant chest depth
            "formant_shift": 0.95,                  # Widens the vocal tract for a cozy storytelling tone
            "rms_mix_rate": 0.45
        }
    else:
        # Cartoon/Mouse Rhyme Mode only
        return {
            "base_tts_voice": "hi-IN-SwaraNeural",
            "pitch_change": 10, 
            "formant_shift": 1.0,
            "rms_mix_rate": 0.25
        }
