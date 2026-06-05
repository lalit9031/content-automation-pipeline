import os
import sys
import shutil
import subprocess
import numpy as np
from pathlib import Path
from gradio_client import Client, handle_file

REF_AUDIO = "/Users/lalitprasadsingh/Desktop/antigravity/Audio/बार्नबी गिलहरी की व्यर्थ खोज.mp3"
FINAL_OUTPUT = "/Users/lalitprasadsingh/Desktop/antigravity/New Audio/LittleBubbles_Generated_Song.mp3"
TEMP_DIR = Path("/Users/lalitprasadsingh/VS_code/content-automation-pipeline/output/.runtime")
TEMP_DIR.mkdir(parents=True, exist_ok=True)
CROPPED_REF = TEMP_DIR / "hindi_ref_cropped_v2.mp3"

# Lyrics cleaned and transliterated (Hinglish phonetics)
lyric = """[verse]
bala gita: krrishna ki sikha
suno bachchom eka pyari kahani,
jo krrishna ne arjuna ko thi sunani|
kurukshetra mem jaba vo ghabaraya,
taba madhava ne yaha patha padhaya|

[verse]
pahala patha: mehanata
karma karo, basa kama pe dhyana,
phala ki chimta chodo aj~nana|
mehanata karana apana dharma,
sachche mana se karo tuma karma|

[verse]
dusara patha: krodha para kabu
gussa hai apana sabase bada dushmana,
isase hi to bhatakega mana|
shamta raho aura sada muskurao,
hara mushkila ko dura bhagao|

[verse]
tisara patha: sabake satha samanata
sabake bhitara ishvara ka vasa,
koi na dura, na koi pasa|
saba jivom se tuma karo pyara,
yahi hai gita ka sachcha sara|

[verse]
chautha patha: nidarata
atma kabhi na marati hai,
phira tu kahe darati hai?
kabhi na daro, basa age badho,
sachchai ki tuma raha pe chalo|

[verse]
gita ki ye batem anamola,
jivana mem tuma mishri si ghola|
kanha ke ye pyare bola,
kholemge saphalata ke pola!"""

def estimate_pitch(audio_path, sample_rate=16000):
    cmd = [
        "ffmpeg", "-y", "-ss", "10", "-t", "20",
        "-i", audio_path, "-ac", "1", "-ar", str(sample_rate),
        "-f", "s16le", "-"
    ]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raw_data, _ = process.communicate()
    except Exception:
        return 0.0

    samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    if len(samples) == 0:
        return 0.0

    frame_size = 1024
    hop_size = 512
    pitches = []
    
    for start in range(0, len(samples) - frame_size, hop_size):
        frame = samples[start:start+frame_size]
        if np.std(frame) < 0.01:
            continue
        corr = np.correlate(frame, frame, mode='full')
        corr = corr[len(corr)//2:]
        min_period = int(sample_rate / 500)
        max_period = int(sample_rate / 80)
        if len(corr) <= max_period:
            continue
        peak_idx = np.argmax(corr[min_period:max_period]) + min_period
        if corr[peak_idx] > 0.3 * corr[0]:
            pitches.append(sample_rate / peak_idx)
            
    if not pitches:
        return 0.0
    return float(np.median(pitches))

def main():
    print("1. Preparing high-vocal style reference (seconds 4.5 to 19.5)...")
    if os.path.exists(REF_AUDIO):
        crop_cmd = [
            "ffmpeg", "-y", "-i", REF_AUDIO,
            "-ss", "4.5", "-t", "15",
            "-codec:a", "libmp3lame", "-b:a", "128k",
            str(CROPPED_REF)
        ]
        print(f"Running command: {' '.join(crop_cmd)}")
        subprocess.run(crop_cmd, check=True)
        prompt_audio_param = handle_file(str(CROPPED_REF))
    else:
        print("ERROR: Reference audio not found!")
        sys.exit(1)
        
    print("\n2. Connecting to tencent/SongGeneration space...")
    client = Client("tencent/SongGeneration", httpx_kwargs={"timeout": 600.0})
    
    trials = [
        {
            "name": "Trial 1 (Playful Female Voice)",
            "desc": (
                "cheerful Indian kids nursery rhyme, playful high-pitched female singing voice, happy bouncy melody, 105 BPM, "
                "clear Hinglish pronunciation, hand claps, glockenspiel, soft harmonium, playful acoustic beats, clean mix."
            )
        },
        {
            "name": "Trial 2 (Animated Child Voice)",
            "desc": (
                "cheerful Indian kids nursery rhyme, animated happy child singing voice, fast bouncy tempo, 108 BPM, "
                "clear Hindi pronunciation, glockenspiel, bells, hand claps, ukulele, acoustic guitar, soft dholak, clean mix."
            )
        }
    ]
    
    best_file = None
    best_pitch_diff = 999.0
    best_trial_info = None
    
    target_pitch = 194.6  # The fundamental pitch of the reference voice
    
    for idx, trial in enumerate(trials, 1):
        print(f"\n--- Running {trial['name']} ---")
        print(f"Description: {trial['desc']}")
        
        try:
            result_path, info = client.predict(
                lyric=lyric,
                description=trial['desc'],
                prompt_audio=prompt_audio_param,
                genre="Auto",
                cfg_coef=2.0,  # Slightly higher CFG for stronger prompt adherence
                temperature=0.75,  # Slightly lower temp for stable generation
                api_name="/generate_song"
            )
            print(f"Space response: {result_path}")
            if not result_path or str(result_path).strip().lower() == "none":
                print("Failed to generate audio for this trial.")
                continue
        except Exception as e:
            print(f"Error generating trial {idx}: {e}")
            continue

        temp_mp3 = TEMP_DIR / f"trial_{idx}_generated.mp3"
        
        # Transcode with 5-second fade-out
        print("Transcoding and applying afade...")
        try:
            # Probe duration
            duration_cmd = [
                "ffprobe", "-i", str(result_path),
                "-show_entries", "format=duration",
                "-v", "quiet", "-of", "csv=p=0"
            ]
            duration_res = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
            total_duration = float(duration_res.stdout.strip())
            
            fade_duration = 5.0
            start_fade = total_duration - fade_duration if total_duration > 15.0 else total_duration * 0.8
            
            transcode_cmd = [
                "ffmpeg", "-y", "-i", str(result_path),
                "-filter:a", f"afade=t=out:st={start_fade:.3f}:d={fade_duration:.3f}",
                "-codec:a", "libmp3lame", "-qscale:a", "2",
                str(temp_mp3)
            ]
            subprocess.run(transcode_cmd, check=True)
        except Exception as e:
            print(f"Transcoding failed: {e}")
            shutil.copy(result_path, temp_mp3)
            
        # Analyze pitch
        pitch = estimate_pitch(str(temp_mp3))
        diff = abs(pitch - target_pitch)
        print(f"Analyzed Vocal Pitch: {pitch:.1f} Hz (Difference from target: {diff:.1f} Hz)")
        
        # We prefer a pitch closer to the target (female/child register)
        # Note: If pitch is 0.0, it means it's silent or instrumentation-only, which we reject.
        if pitch > 120.0 and diff < best_pitch_diff:
            best_pitch_diff = diff
            best_file = temp_mp3
            best_trial_info = trial
            
    if best_file and os.path.exists(best_file):
        print(f"\n==========================================")
        print(f"OPTIMIZATION COMPLETE!")
        print(f"Best trial: {best_trial_info['name']}")
        print(f"Pitch difference: {best_pitch_diff:.1f} Hz")
        
        # Copy to the final destination
        shutil.copy(best_file, FINAL_OUTPUT)
        print(f"Final output saved to: {FINAL_OUTPUT}")
        print(f"==========================================")
    else:
        print("\nERROR: No suitable song was generated in the trials.")
        sys.exit(1)

if __name__ == "__main__":
    main()
