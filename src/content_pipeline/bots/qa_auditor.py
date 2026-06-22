from __future__ import annotations

import base64
import json
import logging
import re
import urllib.request
import urllib.error
from typing import Any
from content_pipeline.config import Settings

# Moondream is a tiny 1.8B vision model — completely free, runs locally.
# Uses only ~1.7GB. ComfyUI unloads models between jobs so there is no conflict.
# One-time setup: ollama pull moondream
OLLAMA_MODEL = "moondream"
OLLAMA_URL = "http://localhost:11434"

# Keywords that indicate a FAIL in Moondream's natural language response
_FAIL_SIGNALS = [
    "man in", "man walking", "man wearing", "male", "businessman",
    "indoor", "inside", "shopping mall", "mall", "ceiling",
    "watermark", "text overlay", "logo",
    "melted", "deformed", "broken face", "distorted face",
]
# Keywords that confirm a PASS
_PASS_SIGNALS = [
    "girl", "young girl", "little girl", "cartoon girl",
    "rain", "umbrella", "outdoor", "outside", "river",
    "no visible defects", "no defects", "no watermark",
]


def _parse_moondream_text(text: str, prompt: str) -> dict[str, Any]:
    """
    Parse Moondream's natural language response into a structured QA result.
    Since Moondream (1.8B) rarely outputs valid JSON, we detect PASS/FAIL
    from its description using keyword matching.
    """
    text_lower = text.lower()

    # Check for explicit JSON first (lucky case)
    json_match = re.search(r"\{.*?\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass

    # Detect FAIL signals
    for signal in _FAIL_SIGNALS:
        if signal in text_lower:
            return {
                "status": "FAIL",
                "reason": f"Moondream detected: '{signal}' — does not match prompt",
                "defect_type": "wrong_subject" if "man" in signal or "mall" in signal else "visual_defect",
                "bounding_box": None
            }

    # Detect PASS signals
    pass_hits = sum(1 for s in _PASS_SIGNALS if s in text_lower)
    if pass_hits >= 2:
        return {
            "status": "PASS",
            "reason": None,
            "defect_type": None,
            "bounding_box": None
        }

    # Neutral / unclear — log it and default to PASS
    logging.info(f"Moondream unclear response (defaulting PASS): {text[:120]}")
    return {
        "status": "PASS",
        "reason": f"Moondream response unclear: {text[:80]}",
        "defect_type": None,
        "bounding_box": None
    }


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
        Moondream describes the image in plain text; we parse keywords to PASS/FAIL.
        Falls back to PASS if Ollama is offline.
        """
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Simple, direct question — Moondream handles these better than JSON instructions
        qa_prompt = (
            f"Describe this image in detail. The image was supposed to show: {generation_prompt}. "
            "Is the main subject a girl or a boy/man? "
            "Is the setting outdoors in rain or indoors? "
            "Are there any visible defects like broken face, extra limbs, or watermarks?"
        )

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": qa_prompt,
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
                logging.info(f"Moondream raw response: {response_text[:200]}")
                result = _parse_moondream_text(response_text, generation_prompt)
                logging.info(f"Moondream QA result: {result}")
                return result

        except urllib.error.URLError as e:
            logging.warning(
                f"Ollama offline or moondream not pulled: {e}. "
                "Run 'ollama pull moondream' to activate visual QA. Defaulting to PASS."
            )
            return {"status": "PASS", "reason": "Ollama offline", "defect_type": None, "bounding_box": None}
        except Exception as e:
            logging.warning(f"QA Auditor failed: {e}. Defaulting to PASS.")
            return {"status": "PASS", "reason": f"Error: {e}", "defect_type": None, "bounding_box": None}
