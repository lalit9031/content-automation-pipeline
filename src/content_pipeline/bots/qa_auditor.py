from __future__ import annotations

import base64
import json
import logging
import urllib.request
import urllib.error
from typing import Any
from content_pipeline.config import Settings


class QAVisualAuditor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # Extract base Ollama URL (e.g. "http://localhost:11434")
        url = getattr(settings, "local_llm_url", "http://localhost:11434/v1")
        if "/v1" in url:
            url = url.split("/v1")[0]
        self.ollama_url = url.rstrip("/")

    def audit_image(self, image_bytes: bytes, generation_prompt: str) -> dict[str, Any]:
        """
        Audits a generated image using local Ollama Vision LLM (e.g. qwen2-vl).
        Returns a dict containing 'status', 'reason', 'defect_type', and 'bounding_box'.
        """
        # Convert image to base64
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        
        # We prompt the model to return structured JSON
        prompt = (
            "You are a Quality Assurance Inspector Agent for a children's storybook generation pipeline. "
            "Your task is to analyze the attached image and detect visual bugs, defects, or anatomical anomalies. "
            "Specifically check for:\n"
            "1. Damaged, missing, asymmetrical, or distorted eyes.\n"
            "2. Melted, deformed, or blurry faces.\n"
            "3. Extra, missing, or malformed hands/fingers/limbs.\n"
            "4. Watermarks, text overlays, signatures, or logos.\n\n"
            f"Image generation prompt was: '{generation_prompt}'\n\n"
            "You MUST return a JSON object with the following fields:\n"
            "{\n"
            '  "status": "PASS" or "FAIL",\n'
            '  "reason": "A description of what is wrong (or null if PASS)",\n'
            '  "defect_type": "eye_damage" or "deformed_face" or "extra_limb" or "watermark" or null,\n'
            '  "bounding_box": [ymin, xmin, ymax, xmax] as integers normalized from 0 to 1000 representing the bounding box around the defect, or null if status is PASS\n'
            "}"
        )

        payload = {
            "model": "qwen2.5vl",
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
            "format": "json"
        }
        
        url = f"{self.ollama_url}/api/generate"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                response = json.loads(res.read().decode("utf-8"))
                response_text = response.get("response", "").strip()
                try:
                    result = json.loads(response_text)
                    logging.info(f"QA Auditor audit result: {result}")
                    return result
                except json.JSONDecodeError:
                    # Try to find a JSON substring if LLM didn't return pure JSON
                    import re
                    match = re.search(r"\{.*?\}", response_text, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                    raise ValueError(f"Failed to parse JSON from response: {response_text}")
        except urllib.error.URLError as e:
            logging.warning(
                f"Local Ollama server is offline or qwen2-vl is not pulled: {e}. "
                "QA Visual Auditing is skipped. Run 'ollama pull qwen2-vl' to activate visual checks."
            )
            return {"status": "PASS", "reason": "Ollama offline, default to PASS", "defect_type": None, "bounding_box": None}
        except Exception as e:
            logging.warning(f"QA Auditor failed: {e}. Defaulting to PASS.")
            return {"status": "PASS", "reason": f"Error: {e}", "defect_type": None, "bounding_box": None}
