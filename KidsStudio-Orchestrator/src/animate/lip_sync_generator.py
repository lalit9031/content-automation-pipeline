import subprocess
import os
from pathlib import Path

def generate_rhubarb_lip_sync(
    audio_input_path: str,
    output_txt_path: str,
    binary_path: str = "./bin/rhubarb"
) -> str:
    """
    Triggers the command-line Rhubarb speech recognition engine locally.
    Outputs a tab-separated (.txt/.tsv) timing sheet for 2D character mouth shapes.
    """
    if not os.path.exists(audio_input_path):
        raise FileNotFoundError(f"⚠️ Source audio voice stem not found: {audio_input_path}")
        
    # Standardize binary path resolution
    resolved_binary = Path(binary_path).resolve()
    if not resolved_binary.exists():
        raise FileNotFoundError(
            f"❌ Rhubarb Lip Sync binary not found at: {resolved_binary}\n"
            f"👉 Please make sure to run the setup script: python scripts/download_rhubarb.py"
        )
        
    print(f"🎬 Rhubarb Core: Analyzing audio frequencies via [{audio_input_path}]...")
    
    # Run Rhubarb native tool directly over terminal sub-process
    # -f tsv: outputs tab-separated timings (Time [s], Mouth Shape [A-X])
    command = [
        str(resolved_binary),
        "-o", output_txt_path,
        "-f", "tsv",
        audio_input_path
    ]
    
    try:
        # Run process
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        if os.path.exists(output_txt_path):
            print(f"🏆 Animation Sheet Success: Exported timing matrix to [{output_txt_path}]")
            return output_txt_path
        else:
            raise RuntimeError(f"Rhubarb finished but output file was not created: {result.stderr}")
            
    except subprocess.CalledProcessError as err:
        error_msg = err.stderr if err.stderr else err.stdout
        raise RuntimeError(f"❌ Rhubarb processing failed: {error_msg}")
