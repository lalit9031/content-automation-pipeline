import os
import argparse
import sys
from pathlib import Path

# Disable Hugging Face Xet extension which hangs on Apple Silicon
os.environ["HF_HUB_DISABLE_XET"] = "1"

# Import machine learning libraries lazily so the Streamlit app can still load
# even if the local voiceover stack is not installed on this machine.
try:
    import torch
    import soundfile as sf
    from transformers import AutoTokenizer
    from parler_tts import ParlerTTSForConditionalGeneration
except ImportError:
    torch = None
    sf = None
    AutoTokenizer = None
    ParlerTTSForConditionalGeneration = None


def generate_local_parler_voiceover(
    text: str,
    output_path: Path,
    *,
    description: str,
    repo_id: str = "ai4bharat/indic-parler-tts",
    token: str | None = None,
) -> Path:
    if torch is None or sf is None or AutoTokenizer is None or ParlerTTSForConditionalGeneration is None:
        raise RuntimeError(
            "Local Parler TTS dependencies are not installed in this environment. "
            "Install torch, soundfile, transformers, and parler_tts to enable the M1 voiceover path."
        )
    device = "cpu"
    if torch.backends.mps.is_available():
        device = "mps"
    dtype = torch.bfloat16
    model = ParlerTTSForConditionalGeneration.from_pretrained(
        repo_id,
        token=token if token else None,
        torch_dtype=dtype,
    ).to(device)
    tokenizer = AutoTokenizer.from_pretrained(
        repo_id,
        token=token if token else None,
    )
    input_ids = tokenizer(description, return_tensors="pt").input_ids.to(device)
    prompt_input_ids = tokenizer(text, return_tensors="pt").input_ids.to(device)
    with torch.no_grad():
        generation = model.generate(input_ids=input_ids, prompt_input_ids=prompt_input_ids)
    audio_arr = generation.cpu().numpy().squeeze()
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), audio_arr, 24000)
    return out_path


def generate_hf_tts_voiceover(
    text: str,
    output_path: Path,
    *,
    model_id: str,
    token: str | None = None,
    provider: str = "fal-ai",
    extra_body: dict | None = None,
) -> Path:
    try:
        from huggingface_hub import InferenceClient
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is required for Hugging Face voiceover options.") from exc

    providers = (provider, "hf-inference") if provider == "fal-ai" else (provider,)
    last_error: Exception | None = None
    audio_bytes: bytes | None = None
    for provider_name in providers:
        try:
            client = InferenceClient(provider=provider_name, api_key=token, timeout=120)
            audio_bytes = client.text_to_speech(
                text,
                model=model_id,
                extra_body=extra_body or None,
            )
            break
        except Exception as exc:
            last_error = exc
            continue
    if audio_bytes is None:
        raise RuntimeError(f"Hugging Face TTS failed for providers {providers}: {last_error}")
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(audio_bytes)
    return out_path

def main():
    if torch is None or sf is None or AutoTokenizer is None or ParlerTTSForConditionalGeneration is None:
        print(
            "❌ Missing required dependency in worker environment: "
            "install torch, soundfile, transformers, and parler_tts"
        )
        sys.exit(1)
    parser = argparse.ArgumentParser(description="Indic Parler-TTS Inference Worker Node")
    parser.add_argument("--text", type=str, required=True, help="Hindi text to synthesize")
    parser.add_argument("--output", type=str, required=True, help="Output wav file path")
    parser.add_argument("--description", type=str, required=True, help="Style prompt description")
    parser.add_argument("--token", type=str, default="", help="Hugging Face hub authentication token")
    args = parser.parse_args()

    # Determine device acceleration
    device = "cpu"
    if torch.backends.mps.is_available():
        device = "mps"
    print(f"💻 Indic-Parler Worker Device: {device}")

    repo_id = "ai4bharat/indic-parler-tts"
    token = args.token or os.environ.get("HF_TOKEN")
    
    # Load model with bfloat16 to save memory and avoid swap/compressor thrashing
    dtype = torch.bfloat16
    print(f"📥 Loading model {repo_id} in {dtype}...")
    try:
        model = ParlerTTSForConditionalGeneration.from_pretrained(
            repo_id, 
            token=token if token else None,
            torch_dtype=dtype
        ).to(device)
        tokenizer = AutoTokenizer.from_pretrained(
            repo_id,
            token=token if token else None
        )
        
        print(f"🎙️ Prompt: {args.text}")
        print(f"🎛️ Description: {args.description}")
        print("🔊 Generating voice...")
        
        # Tokenize inputs
        input_ids = tokenizer(args.description, return_tensors="pt").input_ids.to(device)
        prompt_input_ids = tokenizer(args.text, return_tensors="pt").input_ids.to(device)
        
        # Autoregressive generation
        with torch.no_grad():
            generation = model.generate(input_ids=input_ids, prompt_input_ids=prompt_input_ids)
            
        audio_arr = generation.cpu().numpy().squeeze()
        
        # Ensure output directory exists
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write wav file (24kHz sampling rate for ai4bharat/indic-parler-tts)
        sf.write(str(out_path), audio_arr, 24000)
        print(f"🎉 Audio generated successfully: {out_path} ({out_path.stat().st_size} bytes)")
        
    except Exception as e:
        print(f"❌ Error during model execution: {e}")
        sys.exit(2)

if __name__ == "__main__":
    main()
