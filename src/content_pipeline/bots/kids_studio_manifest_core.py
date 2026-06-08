import re
import numpy as np
import scipy.signal as signal

# ==========================================
# 1. THE ABSOLUTE AUDIO CONFIGURATION MATRIX
# ==========================================
KIDS_STUDIO_MASTER_REGISTRY = {
    "KIDS_RHYME_MOUSE": {
        "display_name": "Squeaky Cartoon Mouse (LittleBubbles Style)",
        "base_tts_voice": "hi-IN-SwaraNeural",
        "pitch_change": 12,                  # Full octave jump for cartoon effect
        "formant_shift": 1.00,               # High-clarity compressed formant range
        "index_rate": 0.40,
        "filter_radius": 3,
        "rms_mix_rate": 0.25,
        "bg_music_prompt": "upbeat electronic kindergarten dance track, 115 BPM, 4/4 clapping rhythm, cheerful arcade synths, bright happy major key"
    },
    "STORY_MALE_PREMIUM": {
        "display_name": "Premium Male Narrator (Wise Baritone Style)",
        "base_tts_voice": "hi-IN-MadhurNeural",
        "pitch_change": -2,                  # Slightly minimized to keep the frequency track stable
        "formant_shift": 0.96,               # Safe throat scaling to prevent gravelly resonance
        "index_rate": 0.22,                  # DECREASED: Wipes out the metallic vowel locking artifact
        "filter_radius": 4,
        "protect": 0.50,                     # High protection gate protects breath blocks
        "rms_mix_rate": 0.35                  # Smooths out low-volume text terminations
    },
    "STORY_FEMALE_KIND": {
        "display_name": "Premium Female Storyteller (Koo Koo TV Style)",
        "base_tts_voice": "hi-IN-SwaraNeural",
        "pitch_change": 0,                   # Hard-locked to zero to eliminate chipmunk leakage
        "formant_shift": 0.98,               # Gently rounds off treble to remove sharp frequencies
        "index_rate": 0.22,                  # DECREASED: Wipes out the metallic vowel locking artifact
        "filter_radius": 3,
        "protect": 0.50,                     # High protection gate protects breath blocks
        "rms_mix_rate": 0.35                  # Smooths out low-volume text terminations
    },
    "EN_KIDS_ANA": {
        "display_name": "Teacher Ana (Preschool Voice - English)",
        "base_tts_voice": "en-US-AnaNeural",
        "pitch_change": 0,
        "formant_shift": 1.00,
        "index_rate": 0.22,                  # DECREASED: Wipes out the metallic vowel locking artifact
        "filter_radius": 3,
        "protect": 0.50,                     # High protection gate protects breath blocks
        "rms_mix_rate": 0.35                  # Smooths out low-volume text terminations
    }
}

# ==========================================
# 2. AUTOMATED LYRIC CLEANING & FILTER CORE
# ==========================================
def cleanse_text_for_vocal_engine(raw_text: str, active_mode: str) -> str:
    """
    Scrubs parenthetical action tokens for storytelling while preserving 
    clean text arrays so the voice engine never reads meta-tags out loud.
    """
    print(f"🧹 Audio Core: Cleansing text stream for active mode: [{active_mode}]")
    
    # Strip any text hidden inside square brackets [like this] or parentheses (like this)
    clean_text = re.sub(r'\[.*?\]', '', raw_text)
    clean_text = re.sub(r'\(.*?\)', '', clean_text)
    
    # Remove loose metadata trigger words that confuse the text-to-speech reader
    clutter_words = ["sad face", "tasty", "juicy", "stretch", "snuggle", "wink", "water water", "clap clap"]
    for word in clutter_words:
        clean_text = re.compile(re.escape(word), re.IGNORECASE).sub('', clean_text)
        
    return re.sub(r' +', ' ', clean_text).strip()

def inject_dynamic_storyteller_pacing(raw_script: str) -> str:
    """
    Replaces static punctuation with variable, natural breathing gaps.
    Prevents the text-to-speech engine from sounding like a rigid machine.
    """
    print("⏳ Audio Core: Injecting dynamic storyteller pacing and sentence breaths...")
    # Create extra-long dramatic pauses for paragraph/scene shifts
    paced_text = raw_script.replace("\n", "... [break] ... ")
    
    # Standard sentence pauses
    paced_text = paced_text.replace("।", "... ")
    paced_text = paced_text.replace(".", "... ")
    
    # Short comma conversational breath pauses
    paced_text = paced_text.replace(",", ", ")
    
    return paced_text

# ==========================================
# 3. HIGH-FIDELITY EQUALIZATION AND WARMTH
# ==========================================
def apply_vocal_equalization(audio_samples: np.ndarray, sr: int, active_mode: str) -> np.ndarray:
    """
    Cleans out sub-bass mud causing the raspy cough distortion, maintains warm 
    mid-bass chest resonance, and tames piercing high-end sharpness.
    Uses custom biquad lowshelf and highshelf structures to prevent scipy crashes.
    """
    if active_mode in ["STORY_MALE_PREMIUM", "STORY_FEMALE_KIND", "EN_KIDS_ANA"]:
        print(f"🎛️ DSP Master: Running throat-clearing filter and stabilizing phase layers for [{active_mode}].")
        import math
        
        # 1. HIGH-PASS FILTER: Cut out everything below 75Hz to stop sub-bass rumble distortion
        b_hpf, a_hpf = signal.butter(N=2, Wn=75.0 / (sr / 2.0), btype='highpass')
        clean_base = signal.lfilter(b_hpf, a_hpf, audio_samples)
        
        # 2. LOW-SHELF BOOST: Add warm chest resonance strictly around 150Hz-200Hz
        # Biquad Low-Shelf Boost (+3.5 dB at 180 Hz)
        def design_biquad_lowshelf(f0, sr, db_gain):
            A = math.pow(10.0, db_gain / 40.0)
            omega = 2.0 * math.pi * f0 / sr
            alpha = math.sin(omega) / 2.0 * math.sqrt(2.0)
            cos_w = math.cos(omega)
            two_sqrt_A_alpha = 2.0 * math.sqrt(A) * alpha
            b0 = A * ((A + 1) - (A - 1) * cos_w + two_sqrt_A_alpha)
            b1 = 2 * A * ((A - 1) - (A + 1) * cos_w)
            b2 = A * ((A + 1) - (A - 1) * cos_w - two_sqrt_A_alpha)
            a0 = (A + 1) + (A - 1) * cos_w + two_sqrt_A_alpha
            a1 = -2 * ((A - 1) + (A + 1) * cos_w)
            a2 = (A + 1) + (A - 1) * cos_w - two_sqrt_A_alpha
            return [b0/a0, b1/a0, b2/a0], [1.0, a1/a0, a2/a0]

        # 3. HIGH-SHELF CUT: Smooth out sharp, biting sibilance frequencies above 4.8kHz
        # Biquad High-Shelf Cut (-4.0 dB at 4800 Hz)
        def design_biquad_highshelf(f0, sr, db_gain):
            A = math.pow(10.0, db_gain / 40.0)
            omega = 2.0 * math.pi * f0 / sr
            alpha = math.sin(omega) / 2.0 * math.sqrt(2.0)
            cos_w = math.cos(omega)
            two_sqrt_A_alpha = 2.0 * math.sqrt(A) * alpha
            b0 = A * ((A + 1) + (A - 1) * cos_w + two_sqrt_A_alpha)
            b1 = -2 * A * ((A - 1) + (A + 1) * cos_w)
            b2 = A * ((A + 1) - (A - 1) * cos_w - two_sqrt_A_alpha)
            a0 = (A + 1) - (A - 1) * cos_w + two_sqrt_A_alpha
            a1 = 2 * ((A - 1) - (A + 1) * cos_w)
            a2 = (A + 1) - (A - 1) * cos_w - two_sqrt_A_alpha
            return [b0/a0, b1/a0, b2/a0], [1.0, a1/a0, a2/a0]

        b_bass, a_bass = design_biquad_lowshelf(180.0, sr, 3.5)
        warmed_audio = signal.lfilter(b_bass, a_bass, clean_base)
        
        b_treble, a_treble = design_biquad_highshelf(4800.0, sr, -4.0)
        return signal.lfilter(b_treble, a_treble, warmed_audio)
        
    print(f"⚡ DSP Master: Bypassing equalizer filters for [{active_mode}] to maintain high-frequency clarity.")
    return audio_samples
