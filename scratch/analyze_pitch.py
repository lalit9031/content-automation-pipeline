import os
import subprocess
import numpy as np

def estimate_pitch(audio_path, start_s=10, duration_s=15, sample_rate=16000):
    # Use ffmpeg to extract raw 16-bit mono PCM at 16kHz
    cmd = [
        "ffmpeg", "-y", "-ss", str(start_s), "-t", str(duration_s),
        "-i", audio_path, "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "-"
    ]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raw_data, stderr = process.communicate()
        if process.returncode != 0:
            print(f"ffmpeg error: {stderr.decode()}")
            return None
    except Exception as e:
        print(f"Error running ffmpeg: {e}")
        return None

    # Convert raw bytes to float32
    samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    if len(samples) == 0:
        return None

    # Frame size of 1024 samples, hop size of 512
    frame_size = 1024
    hop_size = 512
    pitches = []
    
    # Simple autocorrelation method to find fundamental frequency (F0)
    for start in range(0, len(samples) - frame_size, hop_size):
        frame = samples[start:start+frame_size]
        # Skip silent frames
        if np.std(frame) < 0.01:
            continue
            
        # Compute autocorrelation
        corr = np.correlate(frame, frame, mode='full')
        corr = corr[len(corr)//2:]
        
        # We search for pitch between 80Hz and 500Hz
        # Corresponding sample periods:
        min_period = int(sample_rate / 500) # 32 samples
        max_period = int(sample_rate / 80)  # 200 samples
        
        if len(corr) <= max_period:
            continue
            
        # Find peak in the correlation range
        peak_idx = np.argmax(corr[min_period:max_period]) + min_period
        
        # Verify if peak is significant
        if corr[peak_idx] > 0.3 * corr[0]:
            f0 = sample_rate / peak_idx
            pitches.append(f0)
            
    if not pitches:
        return 0.0
    return float(np.median(pitches))

def main():
    ref = "/Users/lalitprasadsingh/Desktop/antigravity/Audio/बार्नबी गिलहरी की व्यर्थ खोज.mp3"
    gen = "/Users/lalitprasadsingh/Desktop/antigravity/New Audio/LittleBubbles_Generated_Song.mp3"
    
    print("Analyzing audio files...")
    
    # Analyze different parts of the reference audio to get a stable estimate
    ref_pitches = []
    for start in [10, 25, 40, 55, 70, 85]:
        p = estimate_pitch(ref, start_s=start, duration_s=10)
        if p and p > 80:
            ref_pitches.append(p)
            
    # Analyze generated audio
    gen_pitches = []
    for start in [10, 25, 40, 55, 70, 85]:
        p = estimate_pitch(gen, start_s=start, duration_s=10)
        if p and p > 80:
            gen_pitches.append(p)
            
    ref_f0 = np.median(ref_pitches) if ref_pitches else 0.0
    gen_f0 = np.median(gen_pitches) if gen_pitches else 0.0
    
    print("\n=== Audio Pitch Analysis ===")
    print(f"Reference File: {os.path.basename(ref)}")
    print(f"  Detected Vocal Pitch: {ref_f0:.1f} Hz")
    
    # Interpret pitch
    if ref_f0 > 240:
        print("  Voice Class: High-pitched Child / Cartoon Voice")
    elif ref_f0 > 180:
        print("  Voice Class: Female Voice (Mid-to-High register)")
    elif ref_f0 > 80:
        print("  Voice Class: Male Voice (Baritone/Tenor register)")
    else:
        print("  Voice Class: Undetermined / Mostly instrumental")
        
    print(f"\nGenerated File: {os.path.basename(gen)}")
    print(f"  Detected Vocal Pitch: {gen_f0:.1f} Hz")
    if gen_f0 > 240:
        print("  Voice Class: High-pitched Child / Cartoon Voice")
    elif gen_f0 > 180:
        print("  Voice Class: Female Voice")
    elif gen_f0 > 80:
        print("  Voice Class: Male Voice")
    else:
        print("  Voice Class: Undetermined")
        
    print("============================\n")

if __name__ == "__main__":
    main()
