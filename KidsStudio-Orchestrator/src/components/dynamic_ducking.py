import os
from pydub import AudioSegment

def mix_vocal_and_music_with_ducking(
    vocal_wav_path: str,
    music_wav_path: str,
    output_mp3_path: str,
    duck_gain_db: float = -14.0,       # Music level when speaking
    idle_gain_db: float = -5.0,        # Music level during pauses
    speech_threshold_dbfs: float = -42.0, # RMS threshold for detecting speech
    window_ms: int = 50,               # Checking window
    attack_ms: int = 150,              # How fast music ducks down
    release_ms: int = 400              # How fast music returns to idle
) -> str:
    """
    Programmatic Sidechain Compressor: Automatically ducks background music
    whenever speech is detected in the vocal stem. Employs attack and release
    ramps to ensure smooth, professional transitions.
    """
    if not os.path.exists(vocal_wav_path):
        raise FileNotFoundError(f"Vocal stem file not found: {vocal_wav_path}")
        
    print("🔊 Mixing down master: Applying sidechain ducking filter to background track...")
    
    # 1. Load stems
    vocals = AudioSegment.from_file(vocal_wav_path)
    
    # Handle missing background music gracefully by outputting clean vocals
    if not music_wav_path or not os.path.exists(music_wav_path):
        print("⚠️ Background music track not found. Exporting vocals-only master.")
        vocals.export(output_mp3_path, format="mp3", bitrate="192k")
        return output_mp3_path
        
    music = AudioSegment.from_file(music_wav_path)
    
    # 2. Match durations and sample rates
    vocals = vocals.set_frame_rate(44100).set_channels(2)
    music = music.set_frame_rate(44100).set_channels(2)
    
    # Loop music if it is shorter than vocals
    if len(music) < len(vocals):
        loop_count = (len(vocals) // len(music)) + 1
        music = music * loop_count
    
    # Trim music to match vocal length precisely
    music = music[:len(vocals)]
    
    # 3. Process window segments to calculate envelope follower gain
    ducked_music = AudioSegment.empty()
    num_windows = len(vocals) // window_ms
    
    # Track smoothed current gain multiplier
    current_gain = idle_gain_db
    
    for i in range(num_windows):
        start_t = i * window_ms
        end_t = start_t + window_ms
        
        vocal_seg = vocals[start_t:end_t]
        music_seg = music[start_t:end_t]
        
        # Detect speech presence by evaluating RMS level
        is_speaking = vocal_seg.dBFS > speech_threshold_dbfs
        
        # Calculate target gain based on speech state
        target_gain = duck_gain_db if is_speaking else idle_gain_db
        
        # Smooth volume transition using attack/release step rates
        if target_gain < current_gain:
            # Attack phase (ducking down): fast step
            step = (current_gain - target_gain) * (window_ms / attack_ms)
            current_gain = max(target_gain, current_gain - step)
        else:
            # Release phase (rising up): slower step
            step = (target_gain - current_gain) * (window_ms / release_ms)
            current_gain = min(target_gain, current_gain + step)
            
        # Apply gain and append segment
        ducked_music += music_seg.apply_gain(current_gain)
        
    # Append any remaining milliseconds
    remainder_ms = len(vocals) % window_ms
    if remainder_ms > 0:
        ducked_music += music[-remainder_ms:].apply_gain(current_gain)
        
    # 4. Master mixdown: overlay vocals on top of ducked music
    master_mix = ducked_music.overlay(vocals)
    
    # Export final audio output
    master_mix.export(output_mp3_path, format="mp3", bitrate="192k")
    print(f"🏆 Mastering Complete: Exported YouTube-ready mixed track to [{output_mp3_path}]")
    return output_mp3_path
