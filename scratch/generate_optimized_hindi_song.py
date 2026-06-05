import os
import sys
import shutil
import subprocess
import re
import numpy as np
from pathlib import Path
from gradio_client import Client, handle_file
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

REF_AUDIO = "/Users/lalitprasadsingh/Desktop/antigravity/Audio/बार्नबी गिलहरी की व्यर्थ खोज.mp3"
FINAL_OUTPUT = "/Users/lalitprasadsingh/Desktop/antigravity/New Audio/LittleBubbles_Generated_Song.mp3"
TEMP_DIR = Path("/Users/lalitprasadsingh/VS_code/content-automation-pipeline/output/.runtime")
TEMP_DIR.mkdir(parents=True, exist_ok=True)
CROPPED_REF = TEMP_DIR / "hindi_ref_cropped_v3.mp3"

raw_lyrics = """बाल गीता: कृष्ण की सीख
सुनो बच्चों एक प्यारी कहानी,
जो कृष्ण ने अर्जुन को थी सुनानी।
कुरुक्षेत्र में जब वो घबराया,
तब माधव ने यह पाठ पढ़ाया।

पहला पाठ: मेहनत (कर्म)
कर्म करो, बस काम पे ध्यान,
फल की चिंता छोड़ो आज्ञान।
मेहनत करना अपना धर्म,
सच्चे मन से करो तुम कर्म।
(अर्थ: हमें सिर्फ अपनी मेहनत और पढ़ाई पर ध्यान ध्यान देना चाहिए, हार-जीत की चिंता नहीं करनी चाहिए।)

दूसरा पाठ: क्रोध पर काबू
गुस्सा है अपना सबसे बड़ा दुश्मन,
इससे ही तो भटकेगा मन।
शांत रहो और सदा मुस्कुराओ,
हर मुश्किल को दूर भगाओ।
(अर्थ: गुस्सा करने से हमारा ही नुकसान होता है। शांत दिमाग से हम कोई भी परेशानी सुलझा सकते हैं।)

तीसरा पाठ: सबके साथ समानता
सबके भीतर ईश्वर का वास,
कोई न दूर, न कोई पास।
सब जीवों से तुम करो प्यार,
यही है गीता का सच्चा सार।
(अर्थ: हमें सबसे प्यार से मिलना चाहिए और किसी के साथ भेदभाव नहीं करना चाहिए।)

चौथा पाठ: निडरता
आत्मा कभी न मरती है,
फिर तू काहे डरती है?
कभी न डरो, बस आगे बढ़ो,
सच्चाई की तुम राह पे चलो।
(अर्थ: हमें कभी किसी चीज़ से डरना नहीं चाहिए और हमेशा सच का साथ देना चाहिए।)

गीता की ये बातें अनमोल,
जीवन में तुम मिश्री सी घोल।
कान्हा के ये प्यारे बोल,
खोलेंगे सफलता के पोल!"""

def indic_to_phonetic_english(devanagari_text: str) -> str:
    itrans = transliterate(devanagari_text, sanscript.DEVANAGARI, sanscript.ITRANS)
    words = itrans.split()
    converted_words = []
    
    for word in words:
        leading_punc = ""
        trailing_punc = ""
        
        while word and not word[0].isalnum() and word[0] not in ['[', ']']:
            leading_punc += word[0]
            word = word[1:]
        while word and not word[-1].isalnum() and word[-1] not in ['[', ']']:
            trailing_punc = word[-1] + trailing_punc
            word = word[:-1]
            
        if not word:
            converted_words.append(leading_punc + trailing_punc)
            continue
            
        if word.startswith("[") and word.endswith("]"):
            converted_words.append(leading_punc + word + trailing_punc)
            continue
            
        w = word
        # 1. Map conjuncts
        w = w.replace("j~n", "gy")
        w = w.replace("kShetra", "kshetra")
        w = w.replace("x", "ksh")
        w = w.replace(".Dh", "dh")
        w = w.replace(".d", "d")
        w = w.replace(".D", "d")
        
        # 2. Map nasalizations (anusvara)
        w = w.replace("oM", "ohn")
        w = w.replace("eM", "mayn")
        w = w.replace("aiM", "ayn")
        w = w.replace("iM", "in")
        w = w.replace("uM", "oon")
        w = w.replace("aM", "an")
        w = w.replace("M", "n")
        
        # 3. Map vowels
        w = w.replace("RRi", "ri")
        w = w.replace("RR", "ri")
        w = w.replace("R", "ri")
        
        # 4. Map 'e' and 'o' to sound-alike English phonics first
        w = w.replace("e", "ay")
        w = w.replace("o", "oh")
        
        # Map case-sensitive ITRANS long vowels
        w = w.replace("A", "aa")
        w = w.replace("I", "ee")
        w = w.replace("U", "oo")
        
        # Map sh/Sh/s
        w = w.replace("Sh", "sh")
        w = w.replace("S", "sh")
        
        # 5. Map short 'a' (schwa) to 'u' or 'uh'
        # If 'a' is at the end of the word (length > 2) and not 'aa', delete it (schwa deletion)
        if w.endswith("a") and not w.endswith("aa") and len(w) > 2:
            w = w[:-1]
            
        # Replace remaining short 'a's with 'u'
        w = re.sub(r'(?<![aeiouy])a(?![aeiouy])', 'u', w)
        
        # 6. Simplify double consonants for better flow (e.g. च्च -> च)
        w = w.replace("chch", "ch")
        
        # Force all lowercase
        w = w.lower()
        
        converted_words.append(leading_punc + w + trailing_punc)
        
    return " ".join(converted_words)

def clean_and_prepare_lyrics(text: str) -> str:
    # 1. Strip parenthetical commentary
    cleaned = re.sub(r"\(अर्थ:[^)]*\)", "", text)
    cleaned = re.sub(r"\([^)]*\)", "", cleaned)
    
    # 2. Transliterate using custom phonetic rules
    phonetic_text = indic_to_phonetic_english(cleaned)
    
    # 3. Format tags (ensure segments start with structure tags)
    lines = [line.strip() for line in phonetic_text.splitlines() if line.strip()]
    sanitized_lines = []
    
    if lines:
        first_line = lines[0]
        if not (first_line.startswith("[") and first_line.endswith("]")):
            sanitized_lines.append("[verse]")
            
        for line in lines:
            if line.startswith("[") and line.endswith("]"):
                tag_content = line[1:-1].lower()
                if "chorus" in tag_content:
                    sanitized_lines.append("[chorus]")
                elif "bridge" in tag_content:
                    sanitized_lines.append("[bridge]")
                else:
                    sanitized_lines.append("[verse]")
            else:
                sanitized_lines.append(line)
                
    # Insert verse tags between stanzas if they are raw blocks
    final_lines = []
    for i, line in enumerate(sanitized_lines):
        if i > 0 and not line.startswith("[") and not sanitized_lines[i-1].startswith("["):
            # If the current line is the start of a heading/stanza, prepend [verse]
            if "paath:" in line or "gita kee" in line or "pahala" in line or "dusara" in line or "tisara" in line or "chautha" in line:
                final_lines.append("[verse]")
        final_lines.append(line)
        
    return "\n".join(final_lines)

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
    print("1. Preparing cleaned phonetic lyrics...")
    processed_lyrics = clean_and_prepare_lyrics(raw_lyrics)
    print("\nOptimized Phonetic Hinglish Lyrics for generation:")
    print(processed_lyrics)
    print("-" * 50)
    
    print("\n2. Preparing style reference audio...")
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
        
    print("\n3. Connecting to tencent/SongGeneration space...")
    client = Client("tencent/SongGeneration", httpx_kwargs={"timeout": 600.0})
    
    trials = [
        {
            "name": "Trial 1 (Playful Female Voice)",
            "desc": (
                "cheerful Indian kids nursery rhyme, bouncy rhythmic recitation, playful high-pitched female voice, happy rhythm, 105 BPM, "
                "clear Hinglish pronunciation, hand claps, glockenspiel, soft harmonium, traditional dholak rhythm, clean mix."
            )
        },
        {
            "name": "Trial 2 (Animated Child Voice)",
            "desc": (
                "cheerful Indian kids nursery rhyme, bouncy kids rhythm, animated happy child voice, fast tempo, 108 BPM, "
                "clear Hindi pronunciation, glockenspiel, bells, hand claps, ukulele, acoustic guitar, soft dholak beats, clean mix."
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
                lyric=processed_lyrics,
                description=trial['desc'],
                prompt_audio=prompt_audio_param,
                genre="Auto",
                cfg_coef=2.0,  # Higher CFG for strong pronunciation adherence
                temperature=0.7,  # Lower temperature for stable vocals
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
