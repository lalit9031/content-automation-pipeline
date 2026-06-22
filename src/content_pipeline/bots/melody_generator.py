import os
import numpy as np
from scipy.io import wavfile

class IndianMusicDSPCore:
    """
    Algorithmic music generator that teaches the bot how to calculate relative 
    Swara intervals, execute Meend glides, and apply microtonal pitch modulations.
    """
    def __init__(self, root_frequency_hz: float = 110.0):
        self.f_root = root_frequency_hz
        # Indian Classical relative ratio map
        self.swara_ratios = {
            "S": 1.0000, "r": 1.0667, "R": 1.1250, "g": 1.2000,
            "G": 1.2500, "m": 1.3333, "M": 1.4063, "P": 1.5000,
            "d": 1.6000, "D": 1.6667, "n": 1.8000, "N": 1.8750
        }

    def get_swara_frequency(self, swara: str, sthayi: str = "mid") -> float:
        """
        Resolves the absolute frequency of a Swara based on the Sthayi (register).
        - mandra (low): 0.50x
        - madhya (mid): 1.00x
        - tara (high): 2.00x
        """
        if swara not in self.swara_ratios:
            return 0.0
        base_f = self.f_root * self.swara_ratios[swara]
        if sthayi.lower() == "low" or sthayi.lower() == "mandra":
            return base_f * 0.50
        elif sthayi.lower() == "high" or sthayi.lower() == "tara":
            return base_f * 2.00
        else:
            return base_f

    def compute_meend_glide(self, f_start: float, f_end: float, num_samples: int) -> np.ndarray:
        """
        Calculates a mathematically smooth Sigmoidal (S-curve) pitch slide 
        between two absolute frequencies to eliminate robotic step jumps.
        """
        if num_samples <= 0:
            return np.array([], dtype=np.float32)
        # Build sigmoidal weight trajectory
        t = np.linspace(-5, 5, num_samples)
        s_curve = 1.0 / (1.0 + np.exp(-t))
        
        # Interpolate the frequency path over the timeline array
        frequency_trajectory = f_start + (f_end - f_start) * s_curve
        return frequency_trajectory

    def generate_andolan_vibrato(self, base_freq: float, num_samples: int, sample_rate: int = 44100) -> np.ndarray:
        """
        Applies a slow, 4Hz microtonal oscillation (Andolan) onto a sustained note.
        Oscillation width = 15 cents.
        """
        if num_samples <= 0:
            return np.array([], dtype=np.float32)
        t = np.arange(num_samples) / sample_rate
        
        # Apply a soft 4Hz frequency modulation curve (oscillation width = 15 cents)
        oscillation_hz = 4.0
        vibrato_depth_hz = base_freq * (15.0 / 1200.0) 
        frequency_curve = base_freq + vibrato_depth_hz * np.sin(2 * np.pi * oscillation_hz * t)
        return frequency_curve


def generate_synthetic_melody_guide(
    duration_seconds: float, 
    tempo_bpm: int, 
    output_path: str, 
    gender: str = "Male",
    speech_path: str = None
) -> str:
    """
    Generates an organic, mathematically sound synthetic melody guide with 
    traditional Indian vocal ornamentations (meend slides, kan swar grace notes, 
    and gamak vibrato) to provide a rich pitch contour grid for RMVPE.
    If speech_path is provided, it performs syllable-aware energy detection
    to lock notes and glides exactly to the spoken vocal phrasing.
    """
    print(f"🎹 Synth Core: Synthesizing a {duration_seconds:.2f}s Indian Vocal Melody Guide ({gender}) at {tempo_bpm} BPM...")
    
    sample_rate = 44100
    total_samples = int(sample_rate * duration_seconds)
    
    # Establish root note (Sa) based on gender
    root_f = 110.0 if gender.lower() == "male" else 220.0
    dsp = IndianMusicDSPCore(root_frequency_hz=root_f)
    
    # Define an emotional melody scale (Bhairavi intervals)
    # Bhairavi notes: S, r, g, m, P, d, n
    bhairavi_notes = [
        ("S", "mid"), ("r", "mid"), ("g", "mid"), ("m", "mid"),
        ("P", "mid"), ("d", "mid"), ("n", "mid"), ("S", "high"),
        ("n", "mid"), ("d", "mid"), ("P", "mid"), ("m", "mid"),
        ("g", "mid"), ("r", "mid"), ("S", "mid")
    ]
    raga_notes = bhairavi_notes
    
    frequency_contour = np.zeros(total_samples, dtype=np.float32)
    amplitude_contour = np.zeros(total_samples, dtype=np.float32)
    
    segments = []
    
    # 1. Try energy-based voiced syllable detection on speech_path
    if speech_path and os.path.exists(speech_path):
        print(f"🎹 Synth Core: Running energy-based syllable detection on: {speech_path}")
        try:
            # Read speech file
            fs, data = wavfile.read(speech_path)
            if len(data.shape) > 1:
                data = data.mean(axis=1)
            data = data.astype(np.float32)
            
            # Normalize amplitude
            max_val = np.max(np.abs(data))
            if max_val > 0.0:
                data /= max_val
                
            sig_duration = len(data) / fs
            
            # Analyze energy in 10ms frames
            frame_len_ms = 10
            hop_len_ms = 10
            frame_size = int(fs * (frame_len_ms / 1000.0))
            hop_size = int(fs * (hop_len_ms / 1000.0))
            
            num_frames = (len(data) - frame_size) // hop_size + 1
            if num_frames > 0:
                energies = np.zeros(num_frames)
                for i in range(num_frames):
                    start = i * hop_size
                    frame = data[start : start + frame_size]
                    energies[i] = np.mean(frame ** 2)
                    
                # Smooth energy curve using moving average (50ms window)
                window_size = 5
                if len(energies) > window_size:
                    kernel = np.ones(window_size) / window_size
                    energies = np.convolve(energies, kernel, mode='same')
                    
                # Set voiced threshold (0.5% of max energy with a reasonable floor)
                voiced_threshold = 0.005 * np.max(energies)
                voiced_threshold = max(voiced_threshold, 1e-4)
                
                is_voiced = energies > voiced_threshold
                
                # Group frames into raw segments
                raw_segments = []
                current_state = is_voiced[0]
                start_frame = 0
                for i in range(1, num_frames):
                    if is_voiced[i] != current_state:
                        start_time = (start_frame * hop_size) / fs
                        end_time = (i * hop_size) / fs
                        raw_segments.append((start_time, end_time, current_state))
                        start_frame = i
                        current_state = is_voiced[i]
                raw_segments.append(((start_frame * hop_size) / fs, sig_duration, current_state))
                
                # Merge short silent gaps (< 150ms) to maintain legato phrasing
                processed_segments = []
                for start, end, voiced in raw_segments:
                    dur = end - start
                    if voiced:
                        if dur >= 0.05:  # Keep voiced segment if >= 50ms
                            processed_segments.append((start, end, True))
                        else:
                            processed_segments.append((start, end, False))
                    else:
                        processed_segments.append((start, end, False))
                        
                # Merge consecutive identical states and bridge short silent gaps
                if processed_segments:
                    curr_start, curr_end, curr_voiced = processed_segments[0]
                    for start, end, voiced in processed_segments[1:]:
                        if curr_voiced and voiced and (start - curr_end < 0.15):
                            # Bridge gap
                            curr_end = end
                        elif curr_voiced == voiced:
                            curr_end = end
                        else:
                            segments.append((curr_start, curr_end, curr_voiced))
                            curr_start = start
                            curr_end = end
                            curr_voiced = voiced
                    segments.append((curr_start, curr_end, curr_voiced))
                    
                print(f"🎹 Synth Core: Successfully extracted {len(segments)} syllable/pause segments.")
        except Exception as err:
            print(f"⚠️ Syllable detection failed: {err}. Falling back to time-based loop.")
            segments = []

    # 2. Build frequency and amplitude contours
    if segments:
        print("🎹 Synth Core: Building syllable-locked raga pitch trajectory...")
        note_idx = 0
        note_steps = [] # tuples of: (start_sample, end_sample, freq, ornament)
        
        for start_t, end_t, voiced in segments:
            start_s = int(start_t * sample_rate)
            end_s = min(int(end_t * sample_rate), total_samples)
            seg_len = end_s - start_s
            if seg_len <= 0:
                continue
                
            if not voiced:
                note_steps.append((start_s, end_s, 0.0, "none"))
            else:
                # Split long voiced blocks into syllable-length notes (approx 400ms beats)
                seg_duration = seg_len / sample_rate
                target_note_len = 0.40
                num_notes = max(1, int(np.round(seg_duration / target_note_len)))
                note_samples = seg_len // num_notes
                
                for k in range(num_notes):
                    sub_start = start_s + k * note_samples
                    sub_end = start_s + (k + 1) * note_samples if k < num_notes - 1 else end_s
                    sub_len = sub_end - sub_start
                    if sub_len <= 0:
                        continue
                        
                    swara, sthayi = raga_notes[note_idx % len(raga_notes)]
                    freq = dsp.get_swara_frequency(swara, sthayi)
                    
                    ornament = "none"
                    if (sub_len / sample_rate) >= 0.30:
                        ornament = "andolan"
                        
                    note_steps.append((sub_start, sub_end, freq, ornament))
                    note_idx += 1
                    
        # Populate initial frequency and amplitude contour from note steps
        for start_s, end_s, freq, ornament in note_steps:
            if freq == 0.0:
                frequency_contour[start_s:end_s] = 0.0
                amplitude_contour[start_s:end_s] = 0.0
            else:
                frequency_contour[start_s:end_s] = freq
                amplitude_contour[start_s:end_s] = 0.50
                
                if ornament == "andolan":
                    frequency_contour[start_s:end_s] = dsp.generate_andolan_vibrato(freq, end_s - start_s, sample_rate)
                    
        # Apply smooth Meend glides (legato pitch transitions) between successive voiced notes
        for j in range(1, len(note_steps)):
            prev_start, prev_end, f1, prev_orn = note_steps[j - 1]
            curr_start, curr_end, f2, curr_orn = note_steps[j]
            
            if f1 > 0.0 and f2 > 0.0 and f1 != f2:
                split_idx = curr_start
                # Compute transition slide range (120ms standard, clamped to half note length)
                max_slide_samples = int(0.12 * sample_rate)
                half_len = min((prev_end - prev_start) // 2, (curr_end - curr_start) // 2)
                slide_half = min(max_slide_samples // 2, half_len)
                
                if slide_half > 0:
                    slide_start = split_idx - slide_half
                    slide_end = split_idx + slide_half
                    slide_len = slide_end - slide_start
                    
                    # Sigmoidal slide curve
                    t = np.linspace(-5, 5, slide_len)
                    s_curve = 1.0 / (1.0 + np.exp(-t))
                    frequency_contour[slide_start:slide_end] = f1 + (f2 - f1) * s_curve
                    
        # Apply Kan Swar grace notes on voiced block start and smooth amplitude envelopes
        for j, (start_s, end_s, freq, ornament) in enumerate(note_steps):
            if freq == 0.0:
                continue
                
            is_onset = (j == 0) or (note_steps[j - 1][2] == 0.0)
            if is_onset:
                # Apply Kan Swar grace note onset slide over first 60ms
                grace_len = min(int(0.06 * sample_rate), (end_s - start_s) // 2)
                if grace_len > 0:
                    grace_start_f = freq * 1.0667  # Slide from a komal semitone above
                    t = np.linspace(-3, 3, grace_len)
                    s_curve = 1.0 / (1.0 + np.exp(-t))
                    frequency_contour[start_s : start_s + grace_len] = grace_start_f + (freq - grace_start_f) * s_curve
                    
                # Apply 30ms amplitude fade-in to prevent audio pops
                fade_in_len = min(int(0.03 * sample_rate), end_s - start_s)
                if fade_in_len > 0:
                    amplitude_contour[start_s : start_s + fade_in_len] *= np.linspace(0.0, 1.0, fade_in_len)
                    
            is_offset = (j == len(note_steps) - 1) or (note_steps[j + 1][2] == 0.0)
            if is_offset:
                # Apply 40ms amplitude fade-out
                fade_out_len = min(int(0.04 * sample_rate), end_s - start_s)
                if fade_out_len > 0:
                    amplitude_contour[end_s - fade_out_len : end_s] *= np.linspace(1.0, 0.0, fade_out_len)
                    
    else:
        # Fallback time-based loop (retains original logic)
        print("🎹 Synth Core: No speech path analyzed. Falling back to time-based loop.")
        melody_steps = [
            ("S", "mid", 2, "kan_swar"),
            ("R", "mid", 2, "meend"),
            ("G", "mid", 4, "andolan"),
            (None, "mid", 1, "none"),
            ("m", "mid", 2, "kan_swar"),
            ("G", "mid", 2, "meend"),
            ("R", "mid", 2, "murki"),
            ("S", "mid", 2, "meend"),
            ("N", "low", 4, "andolan"),
            (None, "mid", 1, "none"),
            ("d", "low", 2, "none"),
            ("S", "mid", 2, "meend"),
            ("G", "mid", 2, "meend"),
            ("R", "mid", 2, "meend"),
            ("S", "mid", 4, "andolan"),
            (None, "mid", 2, "none"),
        ]
        
        beat_duration = 60.0 / tempo_bpm
        curr_idx = 0
        step_idx = 0
        prev_freq = 0.0
        
        while curr_idx < total_samples:
            swara, sthayi, beats, ornament = melody_steps[step_idx % len(melody_steps)]
            step_samples = int(beat_duration * beats * sample_rate)
            end_idx = min(curr_idx + step_samples, total_samples)
            seg_len = end_idx - curr_idx
            
            if seg_len <= 0:
                break
                
            if swara is None:
                frequency_contour[curr_idx:end_idx] = 0.0
                amplitude_contour[curr_idx:end_idx] = 0.0
                prev_freq = 0.0
            else:
                freq = dsp.get_swara_frequency(swara, sthayi)
                freq_array = np.full(seg_len, freq, dtype=np.float32)
                amp_array = np.full(seg_len, 0.50, dtype=np.float32)
                
                if ornament == "meend" and prev_freq > 0.0:
                    slide_samples = min(int(0.25 * sample_rate), seg_len // 2)
                    if slide_samples > 0:
                        freq_array[:slide_samples] = dsp.compute_meend_glide(prev_freq, freq, slide_samples)
                elif ornament == "kan_swar":
                    grace_samples = min(int(0.08 * sample_rate), seg_len // 2)
                    if grace_samples > 0:
                        grace_freq = freq * 1.125
                        freq_array[:grace_samples] = dsp.compute_meend_glide(grace_freq, freq, grace_samples)
                elif ornament == "murki":
                    start_turn = min(int(0.10 * sample_rate), seg_len // 4)
                    turn_duration = min(int(0.20 * sample_rate), seg_len // 2)
                    if start_turn + turn_duration < seg_len:
                        half_turn = turn_duration // 2
                        t_turn1 = np.arange(half_turn) / half_turn
                        t_turn2 = np.arange(half_turn) / half_turn
                        freq_array[start_turn : start_turn + half_turn] = freq * (1.0 + 0.06 * np.sin(np.pi * t_turn1))
                        freq_array[start_turn + half_turn : start_turn + turn_duration] = freq * (1.0 - 0.06 * np.sin(np.pi * t_turn2))
                
                if ornament == "andolan":
                    vib_start_idx = 0
                    if ornament == "meend" and prev_freq > 0.0:
                        vib_start_idx = min(int(0.25 * sample_rate), seg_len // 2)
                    vib_len = seg_len - vib_start_idx
                    if vib_len > 0:
                        freq_array[vib_start_idx:] = dsp.generate_andolan_vibrato(freq, vib_len, sample_rate)
                        
                fade_in_samples = min(int(sample_rate * 0.03), seg_len // 2)
                fade_out_samples = min(int(sample_rate * 0.04), seg_len // 2)
                if fade_in_samples > 0:
                    amp_array[:fade_in_samples] *= np.linspace(0.0, 1.0, fade_in_samples)
                if fade_out_samples > 0:
                    amp_array[-fade_out_samples:] *= np.linspace(1.0, 0.0, fade_out_samples)
                    
                frequency_contour[curr_idx:end_idx] = freq_array
                amplitude_contour[curr_idx:end_idx] = amp_array
                prev_freq = freq
                
            curr_idx = end_idx
            step_idx += 1

    # Phase accumulator to ensure smooth frequency transitions without phase clicks
    phase = np.zeros(total_samples, dtype=np.float64)
    dt = 1.0 / sample_rate
    current_phase = 0.0
    for i in range(total_samples):
        current_phase += 2 * np.pi * frequency_contour[i] * dt
        phase[i] = current_phase
        
    generated_signal = np.sin(phase) * amplitude_contour
    
    # Cast to 16-bit PCM integer wave layout for RVC compliance
    audio_pcm = (generated_signal * 32767).astype(np.int16)
    wavfile.write(output_path, sample_rate, audio_pcm)
    
    print(f"✅ Synth Core: Indian classical DSP melody guide successfully created at: {output_path}")
    return output_path
