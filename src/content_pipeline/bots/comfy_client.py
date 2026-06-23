from __future__ import annotations

import json
import logging
import random
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any


class ComfyUIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout_seconds: int = 300, settings=None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.settings = settings  # Optional Settings object for feature flags

    def _is_listening(self) -> bool:
        try:
            urllib.request.urlopen(self.base_url, timeout=2)
            return True
        except Exception:
            return False

    def _start_server(self) -> tuple[Any, Any]:
        logging.info("[Auto-Memory] Starting ComfyUI server in the background...")
        import subprocess
        import sys
        import os
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:256"

        # Base command — always active flags
        cmd = [
            r"C:\ComfyUI\procgov.exe",
            "--maxmem", "25G",
            "--",
            r"C:\ComfyUI\python_embeded\python.exe",
            "-s",
            r"C:\ComfyUI\ComfyUI\main.py",
            "--windows-standalone-build",
            "--enable-dynamic-vram",
            "--lowvram",
            "--fp8_e4m3fn-unet",       # FP8 UNet weights — saves ~14 GB VRAM vs FP16
            "--fp8_e4m3fn-text-enc",   # FP8 text encoder — already active
        ]

        # Optional: Flash Attention — saves ~2-4 GB VRAM during attention computation
        # Controlled by COMFYUI_USE_FLASH_ATTENTION=true in .env
        use_flash_attn = True  # default on
        if self.settings is not None:
            use_flash_attn = getattr(self.settings, "comfyui_use_flash_attention", True)
        if use_flash_attn:
            cmd.append("--attention-pytorch")
            logging.info("[Auto-Memory] Flash Attention enabled (--attention-pytorch). Saves ~2-4 GB VRAM.")

        # Optional: Tiled VAE decode — saves ~1-2 GB VRAM during decode step
        # Controlled by COMFYUI_USE_TILED_VAE=true in .env
        use_tiled_vae = True  # default on
        if self.settings is not None:
            use_tiled_vae = getattr(self.settings, "comfyui_use_tiled_vae", True)
        if use_tiled_vae:
            cmd.append("--tiled-vae")
            logging.info("[Auto-Memory] Tiled VAE enabled (--tiled-vae). Saves ~1-2 GB VRAM during decode.")

        log_path = Path("comfyui_server_runtime.log")
        log_file = open(log_path, "w", encoding="utf-8")
        # 0x00000040 is IDLE_PRIORITY_CLASS (Low CPU priority on Windows)
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
        if sys.platform == "win32":
            flags |= 0x00000040
        proc = subprocess.Popen(
            cmd,
            cwd=r"C:\ComfyUI",
            stdout=log_file,
            stderr=log_file,
            creationflags=flags
        )
        return proc, log_file

    def _wait_listening(self, timeout: int = 120) -> bool:
        start_time = time.time()
        logging.info("[Auto-Memory] Waiting for ComfyUI server to respond...")
        while time.time() - start_time < timeout:
            if self._is_listening():
                logging.info("[Auto-Memory] ComfyUI server is online and ready.")
                return True
            time.sleep(2)
        logging.error("[Auto-Memory] Timeout waiting for ComfyUI server to start.")
        return False

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))

    def _get(self, endpoint: str) -> dict[str, Any] | bytes:
        url = f"{self.base_url}{endpoint}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as res:
            content_type = res.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return json.loads(res.read().decode("utf-8"))
            return res.read()

    def upload_image(self, image_path: Path) -> str:
        """
        Uploads an image to the ComfyUI server using standard multipart/form-data.
        Returns the uploaded filename name as stored on ComfyUI.
        """
        import requests
        url = f"{self.base_url}/upload/image"
        with open(image_path, "rb") as f:
            files = {"image": (image_path.name, f, "image/png")}
            r = requests.post(url, files=files)
            r.raise_for_status()
            return r.json()["name"]

    def generate(self, workflow: dict[str, Any]) -> list[bytes]:
        """
        Sends the workflow to ComfyUI, waits for it to finish, and returns
        the bytes of all generated output images, gifs, or videos.
        Handles server auto-startup and auto-shutdown to release memory.
        """
        # Ensure a unique client ID
        client_id = f"content_pipeline_{random.randint(1, 1000000)}"
        
        # Post prompt to queue
        payload = {
            "prompt": workflow,
            "client_id": client_id,
        }
        
        import os
        auto_manage = os.getenv("COMFYUI_AUTO_RELEASE_MEMORY", "true").lower() == "true"
        
        started_by_us = False
        proc = None
        log_file = None
        
        if auto_manage:
            if not self._is_listening():
                proc, log_file = self._start_server()
                started_by_us = True
                if not self._wait_listening():
                    if log_file:
                        log_file.close()
                    raise RuntimeError("Failed to start ComfyUI server automatically.")
        
        try:
            try:
                response = self._post("/prompt", payload)
            except urllib.error.URLError as exc:
                err_body = ""
                if hasattr(exc, "read"):
                    try:
                        err_body = exc.read().decode("utf-8")
                    except Exception:
                        pass
                logging.error(f"ComfyUI /prompt error: {exc}. Server response: {err_body}")
                raise RuntimeError(
                    f"Failed to connect to local ComfyUI server at {self.base_url}. "
                    f"Details: {exc}. Response: {err_body}"
                ) from exc
                
            prompt_id = response.get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI response did not contain prompt_id: {response}")

            logging.info(f"Queued ComfyUI job {prompt_id}. Waiting for completion...")
            
            # Poll history for completion
            start_time = time.time()
            completed_data = None
            
            while time.time() - start_time < self.timeout_seconds:
                try:
                    history = self._get(f"/history/{prompt_id}")
                    if isinstance(history, dict) and prompt_id in history:
                        completed_data = history[prompt_id]
                        break
                except Exception:
                    pass
                time.sleep(2)
                
            if not completed_data:
                raise TimeoutError(f"ComfyUI job {prompt_id} timed out after {self.timeout_seconds} seconds.")
                
            # Parse outputs (images, gifs, videos) and retrieve them
            media_bytes_list: list[bytes] = []
            outputs = completed_data.get("outputs", {})
            for node_id, node_output in outputs.items():
                for key in ("images", "gifs", "videos"):
                    if key in node_output:
                        for media_info in node_output[key]:
                            filename = media_info.get("filename")
                            subfolder = media_info.get("subfolder", "")
                            media_type = media_info.get("type", "output")
                            if filename:
                                query = f"filename={filename}&subfolder={subfolder}&type={media_type}"
                                try:
                                    media_bytes = self._get(f"/view?{query}")
                                    if isinstance(media_bytes, bytes):
                                        media_bytes_list.append(media_bytes)
                                except Exception as exc:
                                    logging.warning(f"Failed to fetch {key[:-1]} {filename} from ComfyUI: {exc}")
                                
            return media_bytes_list
        finally:
            if started_by_us and proc:
                logging.info("[Auto-Memory] Terminating ComfyUI server to free RAM/VRAM...")
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                    logging.info("[Auto-Memory] ComfyUI server terminated successfully. RAM/VRAM released.")
                except Exception:
                    logging.warning("[Auto-Memory] ComfyUI server did not terminate in time. Force killing...")
                    proc.kill()
                    proc.wait()
                    logging.info("[Auto-Memory] ComfyUI server force killed. RAM/VRAM released.")
                if log_file:
                    log_file.close()


def load_workflow_json(path_or_str: str | Path) -> dict[str, Any]:
    """Loads a ComfyUI workflow JSON file."""
    path = Path(path_or_str)
    if not path.exists():
        # Return empty dictionary to prevent crash, fallback to mock/another provider will handle it
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def customize_txt2img_workflow(
    workflow: dict[str, Any],
    prompt: str,
    width: int,
    height: int,
    seed: int | None = None,
    model_name: str | None = None,
    negative_prompt: str | None = None,
    sampler_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Attempts to customize a txt2img workflow JSON dynamically.
    Scans all nodes for resolution, text prompt, seed, model checkpoints,
    negative prompt, and sampler settings, making it compatible with
    SD 1.5, SDXL, Flux.1, and custom workflows.
    """
    import copy
    wf = copy.deepcopy(workflow)
    
    if seed is None:
        seed = random.randint(1, 1125899906842624)
        
    for nid, node in wf.items():
        if not isinstance(node, dict) or "inputs" not in node:
            continue
        inputs = node["inputs"]
        if not isinstance(inputs, dict):
            continue

        # 1. Update resolution (width, height)
        # Any node containing BOTH width and height inputs is updated (e.g. EmptyLatentImage)
        if "width" in inputs and "height" in inputs:
            if isinstance(inputs["width"], (int, float)) and isinstance(inputs["height"], (int, float)):
                inputs["width"] = width
                inputs["height"] = height

        # 2. Update positive text prompt
        # Any node containing text-like input fields (text, prompt, positive, text_l, text_g, t5xxl)
        # is updated, unless it contains typical negative prompt words.
        for text_key in ("text", "prompt", "positive", "text_l", "text_g", "t5xxl"):
            if text_key in inputs and isinstance(inputs[text_key], str):
                curr_text = str(inputs[text_key]).lower().strip()
                negative_words = ["negative", "low quality", "bad quality", "ugly", "blurry", "noise", "deformed"]
                if not any(word in curr_text for word in negative_words):
                    inputs[text_key] = prompt

        # 3. Update negative prompt
        if negative_prompt and "negative" in inputs and isinstance(inputs["negative"], str):
            inputs["negative"] = negative_prompt

        # 4. Update sampler settings
        if sampler_config:
            # Update sampler configuration
            for sampler_key in ("sampler_name", "scheduler", "steps", "cfg", "denoise", "guidance"):
                if sampler_key in sampler_config and sampler_key in inputs:
                    if isinstance(sampler_config[sampler_key], (int, float)) and isinstance(inputs[sampler_key], (int, float)):
                        inputs[sampler_key] = sampler_config[sampler_key]
                    elif isinstance(sampler_config[sampler_key], str) and isinstance(inputs[sampler_key], str):
                        inputs[sampler_key] = sampler_config[sampler_key]

        # 5. Update seed
        for seed_key in ("seed", "noise_seed"):
            if seed_key in inputs and isinstance(inputs[seed_key], (int, float)):
                inputs[seed_key] = seed

        # 6. Update checkpoint/model name
        if model_name:
            for ckpt_key in ("ckpt_name", "unet_name", "model_name"):
                if ckpt_key in inputs and isinstance(inputs[ckpt_key], str):
                    inputs[ckpt_key] = model_name

    return wf
