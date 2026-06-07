# Create this module in src/content_pipeline/bots/singing_synthesis.py
import os
import subprocess
import sys
from pathlib import Path

def convert_speech_to_melodic_singing(speech_stem_path: Path, model_filename: str, melody_path: Path = None) -> Path:
    """
    Decoupled Worker Node: Programmatically invokes an isolated Python 3.10 
    environment to run RVC processing, bypassing main environment version blocks.
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
    print(f"🎤 Routing audio to Python 3.10 worker node for explicit singing conversion...")
    try:
        if not worker_script.exists():
            raise FileNotFoundError(f"Worker inference script not found at {worker_script}")
            
        cmd = [
            str(worker_python), str(worker_script),
            "--input", str(speech_stem_path),
            "--output", str(output_singing_path),
            "--model", model_filename,
            "--method", "rmvpe",
            "--index_rate", "0.35"
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
