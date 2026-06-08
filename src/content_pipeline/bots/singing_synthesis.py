import os
import subprocess
import sys
from pathlib import Path
from content_pipeline.bots.singer_manifest import SINGER_MANIFEST, SINGER_ALIASES

def orchestrate_dynamic_vocal_pipeline(selected_singer_key: str, lyrics_text: str = ""):
    """
    Dynamically aligns the base TTS vocoder engine and RVC pitch shifting registers 
    to perfectly match the targeted playback singer's natural anatomy.
    """
    if selected_singer_key == "hi_kids_ananya":
        print("👶 Orchestrator: Configuring pipeline for Baby Ananya (Cute Kid - Hindi)")
        return "shreya", 0
    elif selected_singer_key == "en_kids_ana":
        print("👶 Orchestrator: Configuring pipeline for Teacher Ana (Preschool Voice - English)")
        return "shreya", 0
        
    norm_key = SINGER_ALIASES.get(selected_singer_key, selected_singer_key)

    artist_config = SINGER_MANIFEST.get(norm_key, SINGER_MANIFEST["arijit_singh"])
    artist_gender = artist_config["gender"].lower()
    artist_prefix = artist_config["file_prefix"]
    
    print(f"🎤 Orchestrator: Configuring pipeline for [{artist_config['display_name']}] ({artist_gender})")
    
    # 2. Dynamic TTS assignment - Choose the base voice profile that matches the target gender
    if artist_gender == "female":
        base_tts_voice = "hi-IN-SwaraNeural"  # Pristine native female vocal profile
        vocal_pitch_shift = 0                 # Keep pitch in perfect soprano alignment
    else:
        base_tts_voice = "hi-IN-MadhurNeural" # Warm native male vocal profile
        vocal_pitch_shift = -3                # Introduce deep pop chest resonance
        
    print(f"🤖 Step A: Instantiating Base Vocoder [{base_tts_voice}] with Pitch Shift [{vocal_pitch_shift}] semitones...")
    return artist_prefix, vocal_pitch_shift


def convert_speech_to_melodic_singing(
    speech_stem_path: Path, 
    model_filename: str, 
    melody_path: Path = None,
    index_rate: float = 0.30,
    protect: float = 0.35,
    rms_mix_rate: float = 0.25,
    pitch_shift: int = 0,
    filter_radius: int = 3,
    formant_shift: float = 1.0
) -> Path:
    """
    Decoupled Worker Node: Programmatically invokes an isolated Python 3.10 
    environment to run RVC processing, bypassing main environment version blocks.
    Uses the passed pitch_shift parameter to align register octaves.
    """
    output_singing_path = speech_stem_path.parent / f"mastered_singing_{speech_stem_path.name}"
    
    # Define paths for the isolated legacy environment
    worker_dir = Path("rvc_worker_env")
    worker_python = worker_dir / "bin" / "python" if os.name != "nt" else worker_dir / "Scripts" / "python.exe"
    worker_script = Path("src/content_pipeline/bots/rvc_worker_inference.py")

    # 1. Automated Setup: Build the isolated Python 3.10 worker env if it doesn't exist
    if not worker_dir.exists():
        print("🏗️ Creating Isolated Python 3.10 Worker Environment for RVC...")
        try:
            # Assumes python3.10 is installed on the host system
            subprocess.run(["python3.10", "-m", "venv", str(worker_dir)], check=True)
            
            print("📦 Installing legacy RVC dependencies inside isolated worker...")
            subprocess.run([str(worker_python), "-m", "pip", "install", "rvc-python==0.1.5", "scipy==1.10.1"], check=True)
        except Exception as setup_err:
            print(f"❌ Failed to set up isolated RVC worker environment: {setup_err}")
            print("👉 Falling back to raw speech stem to preserve pipeline execution.")
            return speech_stem_path

    # 2. Execution: Run the voice conversion in the safe, isolated legacy sandbox
    print(f"🎤 Routing audio to Python 3.10 worker node for explicit singing conversion (Shift = {pitch_shift} semitones)...")
    try:
        if not worker_script.exists():
            raise FileNotFoundError(f"Worker inference script not found at {worker_script}")
            
        cmd = [
            str(worker_python), str(worker_script),
            "--input", str(speech_stem_path),
            "--output", str(output_singing_path),
            "--model", model_filename,
            "--method", "rmvpe",
            "--index_rate", str(index_rate),
            "--protect", str(protect),
            "--rms_mix_rate", str(rms_mix_rate),
            "--pitch_shift", str(pitch_shift),
            "--filter_radius", str(filter_radius),
            "--formant_shift", str(formant_shift)
        ]
        if melody_path:
            cmd.extend(["--melody", str(melody_path)])
            
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        print("✨ Worker Node processing complete. Returning high-fidelity singing stem.")
        return output_singing_path

    except Exception as e:
        if isinstance(e, subprocess.CalledProcessError):
            print(f"❌ Isolated Worker Node Failed: {e.stderr}")
        else:
            print(f"❌ RVC Voice Conversion error: {e}")
        print("👉 Falling back to raw speech stem to preserve pipeline execution.")
        return speech_stem_path
