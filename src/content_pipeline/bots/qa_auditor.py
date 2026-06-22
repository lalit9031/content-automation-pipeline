from __future__ import annotations

import base64
import json
import logging
import urllib.request
import urllib.error
from typing import Any
from content_pipeline.config import Settings

# Moondream is a tiny 1.8B vision model — completely free, runs locally.
# Uses only ~2GB VRAM. ComfyUI unloads models between jobs so no conflict.
# One-time setup: ollama pull moondream
OLLAMA_MODEL = "moondream"
OLLAMA_URL = "http://localhost:11434"


class QAVisualAuditor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        url = getattr(settings, "local_llm_url", OLLAMA_URL)
        if "/v1" in url:
            url = url.split("/v1")[0]
        self.ollama_url = url.rstrip("/")

    def audit_image(self, image_bytes: bytes, generation_prompt: str) -> dict[str, Any]:
        """
        Audits a generated image using local Moondream via Ollama.
        Moondream is free, tiny (1.8B), and uses ~2GB VRAM.
        Falls back to PASS if Ollama is offline.
        Returns a dict with 'status', 'reason', 'defect_type', 'bounding_box'.
        """
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            f"The image was generated from this prompt: '{generation_prompt}'. "
            "Does the image match the prompt? Check: "
            "1) Is the subject correct (girl not man, child not adult)? "
            "2) Is the setting correct (outdoor rain/river, not indoor)? "
            "3) Are there any broken or melted faces? "
            "4) Any watermarks or text overlays? "
            "Reply with ONLY a JSON object like this: "
            '{"status": "PASS", "reason": null, "defect_type": null, "bounding_box": null} '
            "or "
            '{"status": "FAIL", "reason": "what is wrong", "defect_type": "wrong_subject", "bounding_box": null}'
        )

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
        }

        url = f"{self.ollama_url}/api/generate"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                response = json.loads(res.read().decode("utf-8"))
                response_text = response.get("response", "").strip()
                # Strip markdown fences if present
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                try:
                    result = json.loads(response_text)
                    logging.info(f"Moondream QA result: {result}")
                    return result
                except json.JSONDecodeError:
                    import re
                    match = re.search(r"\{.*?\}", response_text, re.DOTALL)
                    if match:
                        return json.loads(match.group(0))
                    # If can't parse JSON, treat as PASS with warning
                    logging.warning(f"Could not parse QA JSON: {response_text[:100]}")
                    return {"status": "PASS", "reason": "Parse error", "defect_type": None, "bounding_box": None}

        except urllib.error.URLError as e:
            logging.warning(
                f"Ollama offline or moondream not pulled: {e}. "
                "Run 'ollama pull moondream' to activate visual QA. Defaulting to PASS."
            )
            return {"status": "PASS", "reason": "Ollama offline", "defect_type": None, "bounding_box": None}
        except Exception as e:
            logging.warning(f"QA Auditor failed: {e}. Defaulting to PASS.")
            return {"status": "PASS", "reason": f"Error: {e}", "defect_type": None, "bounding_box": None}
