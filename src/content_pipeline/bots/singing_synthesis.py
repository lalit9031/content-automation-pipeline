# Create this module in src/content_pipeline/bots/singing_synthesis.py
import os
import sys
from pathlib import Path
from scipy.io import wavfile

# Try importing RVC components, falling back to a mock/bypass interface if dependencies fail to compile
try:
    from rvc.modules.vc.modules import VC
    RVC_AVAILABLE = True
except ImportError as err:
    print(f"⚠️ Warning: RVC dependencies could not be imported ({err}). Running in fallback mode.")
    RVC_AVAILABLE = False
    VC = None

def convert_speech_to_melodic_singing(speech_stem_path: Path, model_filename: str) -> Path:
    """
    Acts as the explicit voice processing node. Converts a standard spoken TTS 
    waveform into a pitch-corrected, high-fidelity singing artist voice stem.
    """
    print(f"🎤 Initializing Local RVC Inference Core for: {model_filename}")
    
    output_singing_path = speech_stem_path.parent / f"mastered_singing_{speech_stem_path.name}"
    
    if not RVC_AVAILABLE:
        print("⚠️ RVC-Python is not installed or supported on this environment (requires Python 3.8-3.10 and compiled fairseq).")
        print("👉 Bypassing RVC conversion step and returning the raw TTS stem.")
        return speech_stem_path
        
    # Ensure model file exists
    model_path = Path("models/singers") / f"{model_filename}.pth"
    if not model_path.exists():
        print(f"⚠️ RVC Model {model_path} not found. Please place your .pth model inside models/singers/.")
        print("👉 Falling back to direct raw TTS stem.")
        return speech_stem_path
        
    # Initialize the Retrieval-Based Voice Conversion module
    vc = VC()
    vc.get_vc(str(model_path))
    
    # vc_single processes the audio array, tracking pitch variables dynamically
    target_sample_rate, audio_data, _, _ = vc.vc_single(
        speaker_id=1,
        input_audio_path=speech_stem_path,
        f0_up_key=0,          # Semitone pitch shift adjustment
        f0_method="rmvpe",     # RMVPE is the gold-standard algorithm for singing tracking
        index_rate=0.60,       # Controls target singer accent strength vs clarity
        filter_radius=3        # Reduces breathiness artifacts
    )
    
    # Save the polished vocal stem
    wavfile.write(output_singing_path, target_sample_rate, audio_data)
    
    return output_singing_path
