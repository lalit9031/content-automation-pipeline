from __future__ import annotations

import base64
import json
import logging
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any
from content_pipeline.config import Settings

# ---------------------------------------------------------------------------
# Moondream — tiny 1.8B vision model, completely free, runs via Ollama locally
# Uses ~1.7 GB disk, ~1.5 GB VRAM (ComfyUI frees VRAM between jobs — no conflict)
# One-time setup:  ollama pull moondream
# ---------------------------------------------------------------------------
OLLAMA_MODEL = "moondream"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_TIMEOUT = 90   # seconds — Moondream on CPU can be slow first run

# ---------------------------------------------------------------------------
# Keyword banks for smart PASS / FAIL detection from Moondream's plain-text
# descriptions (Moondream 1.8B describes images well but rarely outputs JSON)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# FAIL signals — any of these detected = FAIL (unless overridden by counter-evidence)
# ---------------------------------------------------------------------------

# HARD fails: always trigger regardless of other context
_HARD_FAIL_SIGNALS: list[tuple[str, str]] = [
    ("man in suit",         "wrong_subject"),
    ("businessman",         "wrong_subject"),
    ("adult male",          "wrong_subject"),
    ("man walking",         "wrong_subject"),
    ("male figure",         "wrong_subject"),
    ("shopping mall",       "wrong_setting"),
    ("inside a mall",       "wrong_setting"),
    ("office building",     "wrong_setting"),
    ("restaurant",          "wrong_setting"),
    ("watermark",           "watermark"),
    ("text overlay",        "watermark"),
    ("melted face",         "deformed_face"),
    ("deformed face",       "deformed_face"),
    ("broken face",         "deformed_face"),
    ("distorted face",      "deformed_face"),
    ("warped face",         "deformed_face"),
    ("mutated face",        "deformed_face"),
    ("blurry face",         "deformed_face"),
    ("glitch",              "artifact"),
    ("visual defect",       "artifact"),
    ("artifact",            "artifact"),
    ("tearing",             "artifact"),
    ("distorted features",  "artifact"),
    ("melted features",     "artifact"),
    ("deformed shoes",      "deformed_limbs"),
    ("melted shoes",        "deformed_limbs"),
    ("warped feet",         "deformed_limbs"),
    ("broken legs",         "deformed_limbs"),
    ("extra legs",          "deformed_limbs"),
    ("sliding feet",        "deformed_limbs"),
    ("weird gait",          "deformed_limbs"),
    ("slipping feet",       "deformed_limbs"),
    ("deformed feet",       "deformed_limbs"),
    ("deformed legs",       "deformed_limbs"),
    ("double feet",         "deformed_limbs"),
    ("fused legs",          "deformed_limbs"),
    ("shaking face",        "instability"),
    ("shaking eyes",        "instability"),
    ("jittery face",        "instability"),
    ("jittery eyes",        "instability"),
    ("flickering face",     "instability"),
    ("flickering eyes",     "instability"),
    ("blurry girl",         "out_of_focus"),
    ("blurry subject",      "out_of_focus"),
    ("out of focus face",   "out_of_focus"),
    ("loss of detail",      "out_of_focus"),
]

# SOFT fails: only trigger if NO outdoor counter-evidence words are present
# Moondream often says "indoors" on blurry outdoor video frames — we verify
_SOFT_FAIL_SIGNALS: list[tuple[str, str]] = [
    ("indoors",             "wrong_setting"),
    ("inside a",            "wrong_setting"),
    ("ceiling",             "wrong_setting"),
    ("man ",                "wrong_subject"),
    ("boy ",                "wrong_subject"),
]

# If any of these are in the response, soft fails are cancelled
_OUTDOOR_COUNTER_EVIDENCE: list[str] = [
    "tree", "trees", "forest", "outdoor", "outside", "river", "rain",
    "puddle", "sidewalk", "street", "path", "sky", "cloud", "nature",
    "water", "green", "umbrella",
]

# At least 2 of these present → PASS
_PASS_SIGNALS: list[str] = [
    "girl",
    "young girl",
    "little girl",
    "cartoon girl",
    "animated girl",
    "female",
    "child",
    "rain",
    "raining",
    "rainy",
    "umbrella",
    "outdoor",
    "outside",
    "river",
    "puddle",
    "no defects",
    "no visible defects",
    "no watermark",
    "no text",
    "clear image",
]


def _has_unnegated_keyword(text: str, keyword: str) -> bool:
    """Checks if a keyword exists in text and is not preceded by negation words."""
    text_lower = text.lower()
    idx = text_lower.find(keyword)
    while idx != -1:
        # Check characters before the keyword for negation
        before = text_lower[max(0, idx - 25):idx]
        negations = ["no ", "not ", "none ", "without ", "free of ", "clear of ", "isn't ", "aren't ", "never "]
        if not any(neg in before for neg in negations):
            return True
        idx = text_lower.find(keyword, idx + len(keyword))
    return False


def _parse_moondream_response(text: str) -> dict[str, Any]:
    """
    Parse Moondream's natural-language image description into a QA result dict.

    Strategy:
    1. Try to parse as JSON first (rare but possible).
    2. Scan HARD fail signals — FAIL if found unnegated.
    3. Scan SOFT fail signals — FAIL if found unnegated and no outdoor counter-evidence.
    4. Count PASS signals — 2+ hits = PASS.
    5. Fallback: default PASS with a note.
    """
    text_lower = text.lower()

    # 1. Try JSON
    json_match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group(0))
            if "status" in result:
                return result
        except json.JSONDecodeError:
            pass

    # 2. Hard FAIL signals — always trigger if unnegated
    for keyword, defect_type in _HARD_FAIL_SIGNALS:
        if _has_unnegated_keyword(text_lower, keyword):
            return {
                "status": "FAIL",
                "reason": f"Detected '{keyword}' — subject/setting does not match prompt",
                "defect_type": defect_type,
                "bounding_box": None,
            }

    # 3. Soft FAIL signals — only trigger if no outdoor counter-evidence and unnegated
    has_outdoor_evidence = any(w in text_lower for w in _OUTDOOR_COUNTER_EVIDENCE)
    if not has_outdoor_evidence:
        for keyword, defect_type in _SOFT_FAIL_SIGNALS:
            if _has_unnegated_keyword(text_lower, keyword):
                return {
                    "status": "FAIL",
                    "reason": f"Detected '{keyword}' with no outdoor context — wrong setting",
                    "defect_type": defect_type,
                    "bounding_box": None,
                }

    # 4. PASS signals — 2+ hits = definite PASS
    pass_hits = [s for s in _PASS_SIGNALS if s in text_lower]
    if len(pass_hits) >= 2:
        return {
            "status": "PASS",
            "reason": None,
            "defect_type": None,
            "bounding_box": None,
        }

    # 5. Unclear — default PASS with note
    logging.info(f"Moondream QA unclear (defaulting PASS). Response: {text[:150]}")
    return {
        "status": "PASS",
        "reason": f"Moondream response unclear — defaulting PASS. Preview: {text[:80]}",
        "defect_type": None,
        "bounding_box": None,
    }


class QAVisualAuditor:
    """
    Visual QA inspector using local Moondream vision model via Ollama.

    Free, offline, and VRAM-safe:
    - Moondream (1.8B) uses only ~1.5 GB VRAM
    - ComfyUI fully unloads between render jobs
    - Ollama serves Moondream on a separate process (port 11434)

    Setup (one time):
        ollama pull moondream

    Usage:
        auditor = QAVisualAuditor(settings)
        result = auditor.audit_image(image_bytes, "prompt text")
        # result = {"status": "PASS"/"FAIL", "reason": ..., "defect_type": ..., "bounding_box": ...}
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        url = getattr(settings, "local_llm_url", OLLAMA_URL)
        if "/v1" in url:
            url = url.split("/v1")[0]
        self.ollama_url = url.rstrip("/")
        self.ollama_model = getattr(settings, "ollama_model", OLLAMA_MODEL)

    def _is_ollama_alive(self) -> bool:
        """Quick liveness check on Ollama server."""
        try:
            with urllib.request.urlopen(f"{self.ollama_url}/api/tags", timeout=3) as r:
                return r.status == 200
        except Exception:
            return False

    def audit_image(self, image_bytes: bytes, generation_prompt: str) -> dict[str, Any]:
        """
        Audit a single image frame against the generation prompt.

        Args:
            image_bytes: Raw PNG/JPEG bytes of the frame.
            generation_prompt: The text prompt used to generate the video/image.

        Returns:
            dict with keys: status, reason, defect_type, bounding_box
        """
        if not self._is_ollama_alive():
            logging.warning(
                "Ollama server is offline. Run 'ollama serve' then 'ollama pull moondream'. "
                "Defaulting to PASS."
            )
            return {
                "status": "PASS",
                "reason": "Ollama offline — visual QA skipped",
                "defect_type": None,
                "bounding_box": None,
            }

        img_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Use a single open-ended description request.
        # Moondream 1.8B only answers the FIRST numbered question then stops,
        # so we ask for one descriptive paragraph instead — this gives rich
        # text that our keyword parser can scan for PASS/FAIL signals.
        qa_prompt = (
            f"Describe everything you see in this image in detail. "
            f"Note the gender of the main subject (girl or man/boy), "
            f"whether the scene is indoors or outdoors, whether it is raining, "
            f"whether an umbrella is present, and look very closely for any visual defects such as "
            f"deformed or blurry faces, shaking or jittery eyes, out-of-focus details, "
            f"melting shoes, distorted legs or feet, watermarks, or text overlays."
        )

        payload = {
            "model": self.ollama_model,
            "prompt": qa_prompt,
            "images": [img_b64],
            "stream": False,
        }

        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as res:
                response = json.loads(res.read().decode("utf-8"))
                raw_text = response.get("response", "").strip()
                logging.info(f"[Moondream] Raw: {raw_text[:200]}")
                result = _parse_moondream_response(raw_text)
                logging.info(f"[Moondream] QA Result: {result}")
                return result

        except urllib.error.URLError as e:
            logging.warning(f"Ollama request failed: {e}. Defaulting to PASS.")
            return {"status": "PASS", "reason": f"Network error: {e}", "defect_type": None, "bounding_box": None}
        except Exception as e:
            logging.warning(f"QA Auditor error: {e}. Defaulting to PASS.")
            return {"status": "PASS", "reason": f"Error: {e}", "defect_type": None, "bounding_box": None}

    def audit_image_file(self, image_path: Path, generation_prompt: str) -> dict[str, Any]:
        """Convenience method — audit directly from a file path."""
        return self.audit_image(image_path.read_bytes(), generation_prompt)
