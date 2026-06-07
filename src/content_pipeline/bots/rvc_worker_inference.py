import argparse
import os
import sys
import requests
import zipfile
import io
from pathlib import Path

# Monkey-patch torch to disable MPS and force CPU execution to prevent segmentation faults
try:
    import torch
    import torch.backends.mps
    torch.backends.mps.is_available = lambda: False
    print("🩹 Disabled MPS in torch to force CPU execution")
except Exception as e:
    print(f"⚠️ Failed to disable MPS: {e}")

# Monkey-patch torch.load to bypass weights_only restrictions in PyTorch 2.6+
try:
    import torch
    original_torch_load = torch.load
    def patched_torch_load(*args, **kwargs):
        kwargs["weights_only"] = False
        return original_torch_load(*args, **kwargs)
    torch.load = patched_torch_load
    print("🩹 Monkey-patched torch.load to force weights_only=False")
except Exception as e:
    print(f"⚠️ Failed to patch torch.load: {e}")

# Monkey-patch faiss.read_index with a pure NumPy KNN search to prevent macOS ARM64 C++ segfaults
try:
    import faiss
    import numpy as np
    original_read_index = faiss.read_index

    class NumPyFaissIndexWrapper:
        def __init__(self, real_index):
            self.real_index = real_index
            self.ntotal = real_index.ntotal
            # Reconstruct the database vectors. Reconstructing does not segfault on macOS.
            self.big_npy = real_index.reconstruct_n(0, self.ntotal)

        def reconstruct_n(self, start, n):
            return self.big_npy[start : start + n]

        def search(self, npy, k=8):
            if npy.ndim == 1:
                npy = np.expand_dims(npy, axis=0)
            X = npy.astype(np.float32)
            Y = self.big_npy.astype(np.float32)
            
            x_norms = np.sum(X**2, axis=1, keepdims=True)  # (L, 1)
            y_norms = np.sum(Y**2, axis=1, keepdims=True).T  # (1, N)
            
            dist_sq = x_norms + y_norms - 2 * np.dot(X, Y.T)  # (L, N)
            dist_sq = np.clip(dist_sq, 0.0, None)
            
            k = min(k, self.ntotal)
            if k <= 0:
                return np.zeros((X.shape[0], 0), dtype=np.float32), np.zeros((X.shape[0], 0), dtype=np.int64)
                
            if k == self.ntotal:
                ix = np.argsort(dist_sq, axis=1)
                row_indices = np.arange(dist_sq.shape[0])[:, None]
                score = dist_sq[row_indices, ix]
                return score.astype(np.float32), ix.astype(np.int64)
                
            partitioned_indices = np.argpartition(dist_sq, k - 1, axis=1)[:, :k]  # (L, k)
            row_indices = np.arange(dist_sq.shape[0])[:, None]
            partitioned_dists = dist_sq[row_indices, partitioned_indices]
            
            sorted_partition_indices = np.argsort(partitioned_dists, axis=1)
            ix = partitioned_indices[row_indices, sorted_partition_indices]
            score = partitioned_dists[row_indices, sorted_partition_indices]
            
            return score.astype(np.float32), ix.astype(np.int64)

    def patched_read_index(*args, **kwargs):
        real_idx = original_read_index(*args, **kwargs)
        return NumPyFaissIndexWrapper(real_idx)

    faiss.read_index = patched_read_index
    print("🩹 Monkey-patched faiss.read_index to run pure NumPy search and prevent macOS ARM64 segfaults")
except Exception as e:
    print(f"⚠️ Failed to monkey-patch faiss.read_index: {e}")

from rvc_python.infer import RVCInference
from rvc_python.modules.vc.pipeline import Pipeline
import librosa
import numpy as np

# Melody Guide Global Configuration
MELODY_GUIDE_AUDIO = None
MELODY_GUIDE_PATH = None

original_get_f0 = Pipeline.get_f0

def patched_get_f0(self, input_audio_path, x, p_len, f0_up_key, f0_method, filter_radius, inp_f0=None):
    global MELODY_GUIDE_AUDIO, MELODY_GUIDE_PATH
    if MELODY_GUIDE_AUDIO is not None:
        print("🎵 Patched get_f0: Snapping pitch extraction to explicit Melody Guide Track...")
        target_len = x.shape[0]
        melody_x = MELODY_GUIDE_AUDIO.copy()
        
        # Length alignment to match x (padding or slicing)
        if len(melody_x) < target_len:
            pad_width = target_len - len(melody_x)
            melody_x = np.pad(melody_x, (0, pad_width), mode='constant', constant_values=0.0)
        else:
            melody_x = melody_x[:target_len]
            
        # Call the original get_f0 with the melody guide track instead of the input speech
        return original_get_f0(self, MELODY_GUIDE_PATH, melody_x, p_len, f0_up_key, f0_method, filter_radius, inp_f0)
    else:
        return original_get_f0(self, input_audio_path, x, p_len, f0_up_key, f0_method, filter_radius, inp_f0)

Pipeline.get_f0 = patched_get_f0

def download_and_extract_model(url: str, dest_pth: Path):
    print(f"📥 Downloading ZIP model from {url}...")
    dest_pth.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, stream=True, timeout=120)
    response.raise_for_status()
    
    zip_data = io.BytesIO()
    for chunk in response.iter_content(chunk_size=8192):
        if chunk:
            zip_data.write(chunk)
            
    print("📦 Extracting RVC model weights...")
    zip_data.seek(0)
    with zipfile.ZipFile(zip_data) as zip_ref:
        pth_extracted = False
        for file_info in zip_ref.infolist():
            filename = Path(file_info.filename).name
            if filename.startswith("."):
                continue
            # Extract .pth weights
            if file_info.filename.endswith(".pth"):
                with zip_ref.open(file_info) as source_file:
                    with open(dest_pth, "wb") as target_file:
                        target_file.write(source_file.read())
                pth_extracted = True
                print(f"✨ Extracted and saved model weights to: {dest_pth}")
                
            # Extract .index file
            if file_info.filename.endswith(".index"):
                dest_index = dest_pth.with_suffix(".index")
                with zip_ref.open(file_info) as source_file:
                    with open(dest_index, "wb") as target_file:
                        target_file.write(source_file.read())
                print(f"✨ Extracted and saved retrieval index to: {dest_index}")
                
        if not pth_extracted:
            raise FileNotFoundError("Could not find a valid .pth file inside the zip archive.")

class AdvancedRVCEngineWrapper:
    """
    Production-grade configuration wrapper for local RVC inference.
    Optimizes pitch extraction grids, formant protection parameters, 
    and vector index blending while enforcing stable CPU computation.
    """
    def __init__(self, model_name: str, device: str = "cpu:0"):
        self.device = device
        self.model_dir = Path("models/singers")
        self.model_path = self.model_dir / f"{model_name}.pth"
        self.index_path = self.model_dir / f"{model_name}.index"
        
        if not self.model_path.exists():
            raise FileNotFoundError(f"Missing mandatory checkpoint weights: {self.model_path}")

    def configure_and_run(self, 
                          input_wav: str, 
                          output_wav: str, 
                          melody_guide: str = None,
                          pitch_shift_semitones: int = 0,
                          index_blend_rate: float = 0.35,
                          pitch_algorithm: str = "rmvpe",
                          smoothing_radius: int = 3):
        """
        Executes advanced signal conversion based on precise studio engineering boundaries.
        """
        print(f"🎛️ Tuning Grid: Method={pitch_algorithm} | Index Rate={index_blend_rate} | Semitones={pitch_shift_semitones} | Filter Radius={smoothing_radius}")
        
        # Enforce host environment configurations to prevent local binary execution crashes
        os.environ["FAISS_NO_AVX2"] = "1"
        
        # 1. Input Signal Normalization: Force strictly mono 16-bit PCM WAV at 16kHz
        try:
            import soundfile as sf
            import librosa
            
            print(f"🎛️ Input Signal Normalization: Loading speech stem {input_wav}...")
            y_speech, _ = librosa.load(str(input_wav), sr=16000, mono=True)
            norm_speech_path = Path(input_wav).parent / f"norm_speech_{Path(input_wav).name}"
            sf.write(str(norm_speech_path), y_speech, 16000, format='WAV', subtype='PCM_16')
            print(f"✨ Normalized speech stem saved to: {norm_speech_path}")
        except Exception as norm_err:
            print(f"⚠️ Signal normalization failed: {norm_err}. Proceeding with raw input.")
            norm_speech_path = Path(input_wav)

        # 2. Melody Guide Setup & Global Configuration
        global MELODY_GUIDE_AUDIO, MELODY_GUIDE_PATH
        if melody_guide:
            melody_file = Path(melody_guide)
            if melody_file.exists():
                print(f"🎵 Loading Melody Guide: {melody_file}")
                try:
                    MELODY_GUIDE_AUDIO, _ = librosa.load(str(melody_file), sr=16000, mono=True)
                    MELODY_GUIDE_PATH = str(melody_file)
                    print(f"✨ Melody Guide loaded successfully. ({len(MELODY_GUIDE_AUDIO)} samples @ 16kHz)")
                except Exception as load_err:
                    print(f"⚠️ Failed to load melody guide: {load_err}")
                    MELODY_GUIDE_AUDIO = None
                    MELODY_GUIDE_PATH = None
            else:
                print(f"⚠️ Melody guide path does not exist: {melody_file}")
        else:
            MELODY_GUIDE_AUDIO = None
            MELODY_GUIDE_PATH = None

        # 3. Initialize RVCInference
        index_file_str = ""
        if self.index_path.exists():
            index_file_str = str(self.index_path)
            print(f"🔎 Found retrieval index file at: {index_file_str}")
        else:
            print("⚠️ Retrieval index file not found. Inference will run without index.")

        try:
            rvc = RVCInference(
                models_dir=str(self.model_dir),
                device=self.device,
                model_path=str(self.model_path),
                index_path=index_file_str,
                version="v2"
            )
            
            # Map parameters directly to the underlying neural execution block
            rvc.set_params(
                f0method=pitch_algorithm,
                index_rate=float(index_blend_rate),
                filter_radius=int(smoothing_radius),
                f0up_key=int(pitch_shift_semitones)
            )
            
            print(f"🎤 Worker: Running voice conversion on: {norm_speech_path}")
            rvc.infer_file(str(norm_speech_path), output_wav)
            
            # Unload model to release resources
            rvc.unload_model()
            print("🎤 Worker: Voice conversion complete!")
            
            # Clean up normalized speech file if created
            if norm_speech_path != Path(input_wav):
                try:
                    if norm_speech_path.exists():
                        os.remove(norm_speech_path)
                except Exception:
                    pass
            return True
            
        except Exception as e:
            sys.stderr.write(f"❌ Core Neural Inference Failed: {str(e)}\n")
            return False

def main():
    parser = argparse.ArgumentParser(description="Isolated RVC Worker Inference Node")
    parser.add_argument("--input", required=True, help="Path to input speech stem wave file")
    parser.add_argument("--output", required=True, help="Path to output singing wave file")
    parser.add_argument("--model", required=True, help="RVC model filename (without .pth)")
    parser.add_argument("--method", default="rmvpe", help="F0 pitch tracking method (e.g. rmvpe)")
    parser.add_argument("--index_rate", type=float, default=0.35, help="RVC index rate")
    parser.add_argument("--melody", help="Path to reference melody audio track (optional)")
    
    args = parser.parse_args()
    
    model_dir = Path("models/singers")
    model_path = model_dir / f"{args.model}.pth"
    
    # If the model does not exist, download the community Arijit Singh RVC model as placeholder/test model
    if not model_path.exists():
        print(f"⚠️ Singer model {model_path} not found.")
        model_url = "https://huggingface.co/ivaan2003/ai-rvc/resolve/main/arijit-singh.zip"
        try:
            download_and_extract_model(model_url, model_path)
        except Exception as e:
            print(f"❌ Failed to download/extract RVC model: {e}")
            raise FileNotFoundError(f"RVC Model file not found at {model_path} and download/extract failed.")
            
    # Instantiate the wrapper and run
    wrapper = AdvancedRVCEngineWrapper(model_name=args.model, device="cpu:0")
    success = wrapper.configure_and_run(
        input_wav=args.input,
        output_wav=args.output,
        melody_guide=args.melody,
        pitch_shift_semitones=0,
        index_blend_rate=args.index_rate,
        pitch_algorithm=args.method,
        smoothing_radius=3
    )
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
