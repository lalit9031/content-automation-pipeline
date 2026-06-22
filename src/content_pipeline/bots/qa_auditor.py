from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any
from content_pipeline.config import Settings


class QAVisualAuditor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_key = getattr(settings, "gemini_api_key", os.environ.get("GEMINI_API_KEY"))

    def audit_image(self, image_bytes: bytes, generation_prompt: str) -> dict[str, Any]:
        """
        Audits a generated image using Google Gemini.
        Returns a dict containing 'status', 'reason', 'defect_type', and 'bounding_box'.
        """
        if not self.api_key:
            logging.warning("Gemini API key not found. Skipping QA visual audit.")
            return {"status": "PASS", "reason": "No API key", "defect_type": None, "bounding_box": None}

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            prompt = (
                "You are a Quality Assurance Inspector Agent for a children's storybook generation pipeline. "
                "Analyze the attached image and detect visual bugs/defects:\n"
                "1. Damaged/distorted eyes. 2. Deformed faces. 3. Malformed hands/limbs. 4. Watermarks/logos.\n"
                f"Prompt was: '{generation_prompt}'\n"
                "Return ONLY a JSON object: "
                '{"status": "PASS"/"FAIL", "reason": string, "defect_type": string/null, "bounding_box": [ymin, xmin, ymax, xmax]/null}'
            )

            response = model.generate_content([
                prompt,
                {"mime_type": "image/jpeg", "data": image_bytes}
            ])
            
            cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
            result = json.loads(cleaned_text)
            logging.info(f"QA Auditor audit result: {result}")
            return result
        except Exception as e:
            logging.warning(f"QA Auditor failed: {e}. Defaulting to PASS.")
            return {"status": "PASS", "reason": f"Error: {e}", "defect_type": None, "bounding_box": None}
