from __future__ import annotations

import io
import logging
import random
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw

from content_pipeline.config import Settings
from content_pipeline.bots.comfy_client import ComfyUIClient, load_workflow_json


class InpaintingEditor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = ComfyUIClient(
            base_url=settings.comfyui_url,
            timeout_seconds=settings.comfyui_timeout_seconds
        )
        self.workflow_path = settings.comfyui_inpaint_workflow
        self.model_name = settings.comfyui_model_name

    def repair_image(
        self,
        image_bytes: bytes,
        bounding_box: list[int],
        defect_type: str | None,
        original_prompt: str
    ) -> bytes:
        """
        Creates a repair mask around the bounding box, uploads image and mask to ComfyUI,
        and runs the inpainting workflow to correct the defect.
        """
        logging.info(f"Inpainting Editor received repair request for defect '{defect_type}' in box {bounding_box}.")
        
        # 1. Load original image to extract dimensions
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        # 2. Map normalized bounding box (0-1000) to actual pixels
        # Box format: [ymin, xmin, ymax, xmax]
        ymin, xmin, ymax, xmax = bounding_box
        
        ymin_px = int((ymin / 1000.0) * height)
        xmin_px = int((xmin / 1000.0) * width)
        ymax_px = int((ymax / 1000.0) * height)
        xmax_px = int((xmax / 1000.0) * width)
        
        # Add a padding margin (e.g. 10%) to the bounding box to capture surrounding style context
        margin_x = int((xmax_px - xmin_px) * 0.15)
        margin_y = int((ymax_px - ymin_px) * 0.15)
        
        ymin_px = max(0, ymin_px - margin_y)
        xmin_px = max(0, xmin_px - margin_x)
        ymax_px = min(height, ymax_px + margin_y)
        xmax_px = min(width, xmax_px + margin_x)
        
        # 3. Create black-and-white binary mask (0 = keep, 255 = inpaint/regenerate)
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle([xmin_px, ymin_px, xmax_px, ymax_px], fill=255)
        
        # 4. Save source image and mask to temporary files
        temp_dir = self.settings.output_dir / ".runtime" / "inpaint_temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        rand_id = random.randint(1000, 9999)
        source_path = temp_dir / f"source_{rand_id}.png"
        mask_path = temp_dir / f"mask_{rand_id}.png"
        
        img.save(source_path, format="PNG")
        mask.save(mask_path, format="PNG")
        
        # 5. Upload both files to ComfyUI
        try:
            uploaded_source = self.client.upload_image(source_path)
            uploaded_mask = self.client.upload_image(mask_path)
        except Exception as exc:
            raise RuntimeError(f"Failed to upload inpaint assets to ComfyUI: {exc}")
        finally:
            # Clean up temp files
            try:
                source_path.unlink(missing_ok=True)
                mask_path.unlink(missing_ok=True)
            except Exception:
                pass

        # 6. Load inpainting workflow JSON
        workflow = load_workflow_json(self.workflow_path)
        if not workflow:
            raise ValueError(
                f"Inpainting workflow JSON at {self.workflow_path} is empty or not found. "
                "Ensure the workflow template is present."
            )

        # 7. Customize workflow
        import copy
        wf = copy.deepcopy(workflow)
        
        # Helper to find nodes by class_type
        def find_nodes(class_type: str) -> list[tuple[str, dict[str, Any]]]:
            return [(nid, node) for nid, node in wf.items() if node.get("class_type") == class_type]

        # Update LoadImage nodes
        # We need to map source to the node loading the original image, and mask to the mask loader.
        # To distinguish, we look at the inputs or check sequentially:
        # LoadImage node 1 is typically source, node 2 is mask (or we look at connected edges)
        load_image_nodes = find_nodes("LoadImage")
        if len(load_image_nodes) >= 2:
            # Match by node ID or inputs
            nid_1, node_1 = load_image_nodes[0]
            nid_2, node_2 = load_image_nodes[1]
            
            # Map based on file name or simple order
            node_1["inputs"]["image"] = uploaded_source
            node_2["inputs"]["image"] = uploaded_mask
        else:
            # Fallback if only 1 LoadImage node found
            for nid, node in load_image_nodes:
                if "inputs" in node:
                    node["inputs"]["image"] = uploaded_source

        # Formulate corrective inpaint prompt based on defect type
        if defect_type == "eye_damage":
            inpaint_prompt = "a perfectly detailed Pixar 3D animated eye, matching eye, clear iris, symmetrical, highly detailed, cute children style"
        elif defect_type == "deformed_face":
            inpaint_prompt = "a perfectly rendered, symmetrical, cute Pixar-style face of a child, smiling, clear facial features"
        elif defect_type == "extra_limb":
            inpaint_prompt = "clean background, empty grass, remove extra fingers/limbs, matching background texture"
        else:
            inpaint_prompt = f"clean and fix details, matching the style of: {original_prompt}"

        logging.info(f"Formulated inpainting prompt: '{inpaint_prompt}'")

        # Update CLIPTextEncode (positive prompt)
        text_nodes = find_nodes("CLIPTextEncode")
        for _, node in text_nodes:
            if "inputs" in node and "text" in node["inputs"]:
                curr_text = str(node["inputs"]["text"]).lower().strip()
                negative_words = ["negative", "low quality", "bad quality", "ugly", "blurry", "noise"]
                if not any(word in curr_text for word in negative_words):
                    node["inputs"]["text"] = inpaint_prompt

        # Update KSampler seed
        seed = random.randint(1, 1125899906842624)
        sampler_nodes = find_nodes("KSampler") + find_nodes("KSamplerAdvanced") + find_nodes("SamplerCustomAdvanced")
        for _, node in sampler_nodes:
            if "inputs" in node:
                for seed_key in ("seed", "noise_seed"):
                    if seed_key in node["inputs"]:
                        node["inputs"][seed_key] = seed

        # Update Checkpoint model
        if self.model_name:
            loader_nodes = find_nodes("CheckpointLoaderSimple") + find_nodes("UNETLoader")
            for _, node in loader_nodes:
                if "inputs" in node:
                    for ckpt_key in ("ckpt_name", "unet_name"):
                        if ckpt_key in node["inputs"]:
                            node["inputs"][ckpt_key] = self.model_name

        # 8. Generate inpainted image
        repaired_list = self.client.generate(wf)
        if not repaired_list:
            raise RuntimeError("ComfyUI inpainting completed but returned no output image.")

        return repaired_list[0]
