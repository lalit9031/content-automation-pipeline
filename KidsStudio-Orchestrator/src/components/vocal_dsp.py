import os
import numpy as np
from pathlib import Path
from pydub import AudioSegment
from scipy.signal import butter, lfilter

def butter_highpass(cutoff, fs, order=5):
    """
    Computes Butterworth high-pass filter coefficients.
    """
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='high', analog=False)
    return b, a

def butter_highpass_filter(data, cutoff, fs, order=5):
    """
    Applies high-pass filter to signal array.
    """
    b, a = butter_highpass(cutoff, fs, order=order)
    y = lfilter(b, a, data)
    return y

def apply_low_shelf_warmth(data, fs, gain_db=3.0, cutoff_hz=200.0):
    """
    Applies a low-shelf filter to boost chest resonance (warmth).
    """
    # Design low-shelf filter coefficients
    w0 = 2 * np.pi * cutoff_hz / fs
    alpha = np.sin(w0) / 2 * np.sqrt(2) # Q = 0.707
    A = 10 ** (gain_db / 40.0)
    
    # Low-shelf filter coefficients formula
    b0 = A * ((A + 1) - (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha)
    b1 = 2 * A * ((A - 1) - (A + 1) * np.cos(w0))
    b2 = A * ((A + 1) - (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha)
    a0 = (A + 1) + (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha
    a1 = -2 * ((A - 1) + (A + 1) * np.cos(w0))
    a2 = (A + 1) + (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha
    
    b = np.array([b0, b1, b2]) / a0
    a = np.array([a0, a1, a2]) / a0
    
    y = lfilter(b, a, data)
    return y

def apply_vocal_dsp_chain(
    input_wav_path: str,
    output_wav_path: str,
    hpf_cutoff: float = 85.0,
    warmth_boost_db: float = 2.5,
    warmth_cutoff: float = 220.0
) -> str:
    """
    Executes the clean close-mic vocal DSP chain over a WAV stem.
    Removes low-end rumble (HPF) and adds low-shelf chest resonance.
    """
    if not os.path.exists(input_wav_path):
        raise FileNotFoundError(f"Source vocal track not found: {input_wav_path}")
        
    print(f"🎛️ DSP Vocal EQ: Applying HPF ({hpf_cutoff}Hz) & Low-shelf boost (+{warmth_boost_db}dB)...")
    try:
        # 1. Load audio file via pydub
        sound = AudioSegment.from_file(input_wav_path)
        fs = sound.frame_rate
        
        # Convert to numpy float array
        samples = np.array(sound.get_array_of_samples(), dtype=np.float32)
        
        # Handle stereo signals
        if sound.channels == 2:
            left = samples[0::2]
            right = samples[1::2]
            
            # Filter left
            left_filt = butter_highpass_filter(left, hpf_cutoff, fs)
            left_filt = apply_low_shelf_warmth(left_filt, fs, warmth_boost_db, warmth_cutoff)
            
            # Filter right
            right_filt = butter_highpass_filter(right, hpf_cutoff, fs)
            right_filt = apply_low_shelf_warmth(right_filt, fs, warmth_boost_db, warmth_cutoff)
            
            # Interleave
            filtered_samples = np.empty_like(samples)
            filtered_samples[0::2] = left_filt
            filtered_samples[1::2] = right_filt
        else:
            # Mono filtering
            filtered_samples = butter_highpass_filter(samples, hpf_cutoff, fs)
            filtered_samples = apply_low_shelf_warmth(filtered_samples, fs, warmth_boost_db, warmth_cutoff)
            
        # Convert back to original bit depth
        if sound.sample_width == 2:
            filtered_samples = np.clip(filtered_samples, -32768, 32767).astype(np.int16)
        elif sound.sample_width == 4:
            filtered_samples = np.clip(filtered_samples, -2147483648, 2147483647).astype(np.int32)
        else:
            filtered_samples = np.clip(filtered_samples, -128, 127).astype(np.int8)
            
        # Export as a new WAV file
        filtered_sound = sound._spawn(filtered_samples.tobytes())
        filtered_sound.export(output_wav_path, format="wav")
        
        print(f"✨ DSP Chain Complete: Saved optimized vocals to [{output_wav_path}]")
        return output_wav_path
        
    except Exception as e:
        print(f"⚠️ DSP Vocal chain warning: {e}. Falling back to original audio.")
        # Fallback to copy the original file
        try:
            sound = AudioSegment.from_file(input_wav_path)
            sound.export(output_wav_path, format="wav")
            return output_wav_path
        except:
            return input_wav_path
