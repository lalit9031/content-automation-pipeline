from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import gradio as gr
import spaces
import torch
from diffusers import StableVideoDiffusionPipeline
from diffusers.utils import export_to_video
from PIL import Image, ImageOps


DEFAULT_MODEL_ID = os.getenv(
    "HF_ZERO_GPU_VIDEO_MODEL",
    "stabilityai/stable-video-diffusion-img2vid-xt-1-1",
)
DEFAULT_GPU_DURATION_SECONDS = 60
DEFAULT_FPS = int(os.getenv("HF_ZERO_GPU_FPS", "6"))
DEFAULT_NUM_FRAMES = int(os.getenv("HF_ZERO_GPU_NUM_FRAMES", "16"))
DEFAULT_INFERENCE_STEPS = int(os.getenv("HF_ZERO_GPU_INFERENCE_STEPS", "12"))
DEFAULT_MOTION_BUCKET_ID = int(os.getenv("HF_ZERO_GPU_MOTION_BUCKET_ID", "127"))
DEFAULT_NOISE_AUG_STRENGTH = float(os.getenv("HF_ZERO_GPU_NOISE_AUG_STRENGTH", "0.02"))

_PIPELINE: StableVideoDiffusionPipeline | None = None


def _load_pipeline(model_id: str) -> StableVideoDiffusionPipeline:
    global _PIPELINE
    if _PIPELINE is not None and getattr(_PIPELINE, "_model_id", "") == model_id:
        return _PIPELINE
    try:
        pipe = StableVideoDiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.float16,
            variant="fp16",
            use_safetensors=True,
        )
    except Exception as exc:
        if exc.__class__.__name__ == "GatedRepoError":
            raise RuntimeError(
                f"Model '{model_id}' is gated. Open the model page in Hugging Face, "
                "request/accept access with the same account that owns the HF_TOKEN secret, "
                "then restart this Space."
            ) from exc
        raise
    pipe.enable_model_cpu_offload()
    pipe._model_id = model_id  # type: ignore[attr-defined]
    _PIPELINE = pipe
    return pipe


def _safe_extract(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            target = destination / member.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            if member.is_dir():
                continue
            with archive.open(member, "r") as source, open(target, "wb") as sink:
                shutil.copyfileobj(source, sink)


def _zip_directory(source_root: Path, zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in source_root.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, arcname=file_path.relative_to(source_root).as_posix())
    return zip_path


def _render_clip(
    pipe: StableVideoDiffusionPipeline,
    image_path: Path,
    output_path: Path,
    *,
    num_frames: int,
    inference_steps: int,
    motion_bucket_id: int,
    fps: int,
    noise_aug_strength: float,
    seed: int,
) -> None:
    image = Image.open(image_path).convert("RGB")
    target_size = (768, 432) if image.width >= image.height else (432, 768)
    image = ImageOps.fit(image, target_size, method=Image.Resampling.LANCZOS)
    generator = torch.Generator(device="cuda").manual_seed(seed)
    result = pipe(
        image,
        num_frames=num_frames,
        num_inference_steps=inference_steps,
        motion_bucket_id=motion_bucket_id,
        fps=fps,
        noise_aug_strength=noise_aug_strength,
        decode_chunk_size=8,
        generator=generator,
    )
    frames = result.frames[0] if hasattr(result, "frames") else result[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_to_video(frames, str(output_path), fps=fps)


@spaces.GPU(duration=DEFAULT_GPU_DURATION_SECONDS)
def render_package(
    package_zip: str,
    model_id: str,
    num_frames: int,
    inference_steps: int,
    motion_bucket_id: int,
    fps: int,
    noise_aug_strength: float,
    seed: int,
) -> str:
    run_root = Path(tempfile.mkdtemp(prefix="zero_gpu_video_"))
    input_root = run_root / "input"
    output_root = run_root / "output"
    input_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    _safe_extract(Path(package_zip), input_root)
    episode_path = input_root / "episode.json"
    if not episode_path.exists():
        raise FileNotFoundError("episode.json missing from input package.")

    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    pipe = _load_pipeline(model_id or DEFAULT_MODEL_ID)

    for index, clip in enumerate(episode.get("clips", []), start=1):
        if clip.get("source_type") != "auto_2_5d":
            continue
        image_name = Path(str(clip["expected_file"])).with_suffix(".png").name
        image_path = input_root / "clips" / "auto_2_5d" / image_name
        if not image_path.exists():
            raise FileNotFoundError(f"Missing input still: {image_path}")
        video_path = output_root / "clips" / "auto_2_5d" / clip["expected_file"]
        render_seed = seed + index
        _render_clip(
            pipe,
            image_path,
            video_path,
            num_frames=max(8, min(int(num_frames), 16)),
            inference_steps=max(10, min(int(inference_steps), 12)),
            motion_bucket_id=int(motion_bucket_id),
            fps=max(4, min(int(fps), 6)),
            noise_aug_strength=float(noise_aug_strength),
            seed=render_seed,
        )

    rendered_zip = run_root / "rendered_clips.zip"
    _zip_directory(output_root, rendered_zip)
    return str(rendered_zip)


with gr.Blocks(title="ZeroGPU Video Render Space") as demo:
    gr.Markdown(
        """
        # ZeroGPU Video Render Space
        Upload a packaged episode zip containing `episode.json` and scene stills.
        The space renders `auto_2_5d` clips as animated MP4s and returns a zip
        that can be dropped back into the main studio workspace.
        """
    )

    package_zip = gr.File(label="Episode package zip", file_count="single", type="filepath")
    model_id = gr.Textbox(
        label="Video model",
        value=DEFAULT_MODEL_ID,
        info="Override the video model if needed. Defaults to a Stable Video Diffusion image-to-video model.",
    )
    with gr.Row():
        num_frames = gr.Slider(8, 49, value=DEFAULT_NUM_FRAMES, step=1, label="Frames")
        inference_steps = gr.Slider(10, 50, value=DEFAULT_INFERENCE_STEPS, step=1, label="Inference steps")
    with gr.Row():
        motion_bucket_id = gr.Slider(0, 255, value=DEFAULT_MOTION_BUCKET_ID, step=1, label="Motion bucket")
        fps = gr.Slider(4, 30, value=DEFAULT_FPS, step=1, label="FPS")
    noise_aug_strength = gr.Slider(
        0.0,
        0.2,
        value=DEFAULT_NOISE_AUG_STRENGTH,
        step=0.01,
        label="Noise augmentation",
    )
    seed = gr.Number(value=42, label="Seed", precision=0)
    render_btn = gr.Button("Render Package", variant="primary")
    output_zip = gr.File(label="Rendered clips zip", file_count="single", type="filepath")

    render_btn.click(
        fn=render_package,
        inputs=[package_zip, model_id, num_frames, inference_steps, motion_bucket_id, fps, noise_aug_strength, seed],
        outputs=output_zip,
        api_name="/render_package",
    )


if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch()
