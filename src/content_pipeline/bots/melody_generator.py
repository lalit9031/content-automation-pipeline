import numpy as np
from scipy.io import wavfile

def generate_synthetic_melody_guide(duration_seconds: float, tempo_bpm: int, output_path: str) -> str:
    """
    Generates a clear, mathematically sound pure sine-wave synth reference 
    track based on the song's key. Provides a clean pitch contour grid for RMVPE.
    """
    print(f"🎹 Synth Core: Synthesizing a {duration_seconds}s Melody Guide Track at {tempo_bpm} BPM...")
    
    sample_rate = 44100
    total_samples = int(sample_rate * duration_seconds)
    time_array = np.linspace(0, duration_seconds, total_samples, endpoint=False)
    
    # Define a clean romantic ballad progression frequencies (C-Major/A-Minor)
    # C4 (261.63 Hz), G3 (196.00 Hz), Am3 (220.00 Hz), F3 (174.61 Hz)
    chord_frequencies = [261.63, 196.00, 220.00, 174.61]
    samples_per_chord = int(total_samples / len(chord_frequencies))
    
    generated_signal = np.zeros(total_samples, dtype=np.float32)
    
    # Construct continuous melodic sweeps across the duration timeline
    for idx, freq in enumerate(chord_frequencies):
        start_idx = idx * samples_per_chord
        end_idx = min(start_idx + samples_per_chord, total_samples)
        seg_len = end_idx - start_idx
        if seg_len <= 0:
            continue
        
        t_segment = time_array[start_idx:end_idx]
        sig = np.sin(2 * np.pi * freq * t_segment) * 0.50
        
        # Apply 10ms envelope fades at chord transitions to avoid transient clicks
        fade_samples = min(int(sample_rate * 0.01), seg_len // 2)
        if fade_samples > 0:
            fade_in = np.linspace(0.0, 1.0, fade_samples)
            fade_out = np.linspace(1.0, 0.0, fade_samples)
            sig[:fade_samples] *= fade_in
            sig[-fade_samples:] *= fade_out
            
        generated_signal[start_idx:end_idx] = sig
        
    # Cast to 16-bit PCM integer wave layout for standard RVC file compliance
    audio_pcm = (generated_signal * 32767).astype(np.int16)
    wavfile.write(output_path, sample_rate, audio_pcm)
    
    return output_path
