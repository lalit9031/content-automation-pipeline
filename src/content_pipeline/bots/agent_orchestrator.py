from __future__ import annotations

import logging
from typing import Any

from content_pipeline.config import Settings
from content_pipeline.bots.qa_auditor import QAVisualAuditor
from content_pipeline.bots.inpainting_editor import InpaintingEditor


class AgentOrchestrator:
    def __init__(self, settings: Settings, max_attempts: int = 3) -> None:
        self.settings = settings
        self.max_attempts = max_attempts
        self.auditor = QAVisualAuditor(settings)
        self.editor = InpaintingEditor(settings)

    def run_image_audit_repair_loop(self, raw_image_bytes: bytes, generation_prompt: str) -> bytes:
        """
        Coordinates the multi-agent generation validation and auto-correction loop.
        Inspected by QA Auditor. Defective zones are automatically repaired by Inpainting Editor.
        """
        current_image = raw_image_bytes
        
        logging.info("Starting Multi-Agent Image Quality Assurance and Repair loop.")

        for attempt in range(1, self.max_attempts + 1):
            logging.info(f"QA Loop: Attempt {attempt} of {self.max_attempts}...")
            
            # 1. Audit the image
            audit_result = self.auditor.audit_image(current_image, generation_prompt)
            
            status = audit_result.get("status", "PASS").upper()
            reason = audit_result.get("reason", "No reason provided.")
            
            if status == "PASS":
                logging.info(f"QA Loop succeeded on attempt {attempt}. Audit: PASS. Reason: {reason}")
                return current_image
            
            # Image has a defect, extract correction parameters
            defect_type = audit_result.get("defect_type")
            bounding_box = audit_result.get("bounding_box")
            
            logging.warning(
                f"QA Loop detected visual defect on attempt {attempt}: "
                f"Defect type: '{defect_type}'. Reason: '{reason}'. Bounding box: {bounding_box}"
            )
            
            if not bounding_box or not isinstance(bounding_box, list) or len(bounding_box) != 4:
                logging.warning("Defect bounding box is missing or invalid. Cannot run target inpainting. Ending loop.")
                return current_image

            # 2. Trigger inpaint correction
            try:
                current_image = self.editor.repair_image(
                    image_bytes=current_image,
                    bounding_box=bounding_box,
                    defect_type=defect_type,
                    original_prompt=generation_prompt
                )
                logging.info(f"Inpainting Editor successfully repaired the image on attempt {attempt}.")
            except Exception as exc:
                logging.error(f"Inpainting Editor failed to repair image on attempt {attempt}: {exc}. Ending loop.")
                return current_image

        logging.warning(f"QA Loop exhausted all {self.max_attempts} attempts without reaching a PASS status. Returning last render.")
        return current_image
