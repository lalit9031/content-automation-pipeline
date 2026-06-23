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
# Layer 1: Pixel-Level QA (pure Python stdlib, zero AI, instant)
# Catches: blurry frames, corrupt VAE decodes, black/flat frames, tiny files.
# Runs BEFORE Moondream on every sampled frame.
# ---------------------------------------------------------------------------

def _compute_sharpness(png_bytes: bytes) -> float:
    """Laplacian variance sharpness score. Score guide: below 30=blurry, 30-80=soft, above 80=sharp."""
    import struct, zlib
    try:
        if len(png_bytes) < 100 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
            return 100.0
        pos, width, height, idat = 8, 0, 0, b""
        while pos + 12 <= len(png_bytes):
            n = struct.unpack(">I", png_bytes[pos:pos+4])[0]
            ct = png_bytes[pos+4:pos+8]
            d = png_bytes[pos+8:pos+8+n]
            if ct == b"IHDR" and len(d) >= 8:
                width, height = struct.unpack(">II", d[:8])
            elif ct == b"IDAT":
                idat += d
            elif ct == b"IEND":
                break
            pos += 12 + n
        if not idat or not width:
            return 100.0
        raw = zlib.decompress(idat)
        rs = width * 3 + 1
        rows = []
        for i in range(min(height, len(raw) // max(rs, 1))):
            row = raw[i*rs+1:i*rs+rs]
            rows.append([int(0.299*row[j]+0.587*row[j+1]+0.114*row[j+2]) for j in range(0, len(row)-2, 3)])
        if len(rows) < 3:
            return 100.0
        s, c = 0.0, 0
        for r in range(1, len(rows)-1, 4):
            w = min(len(rows[r]), len(rows[r-1]), len(rows[r+1]))
            for col in range(1, w-1, 4):
                s += abs(4*rows[r][col]-rows[r-1][col]-rows[r+1][col]-rows[r][col-1]-rows[r][col+1])
                c += 1
        return (s / c) if c > 0 else 100.0
    except Exception:
        return 100.0


def _brightness_stats(png_bytes: bytes):
    """Returns (mean, std) brightness. Detects all-black or flat corrupt frames."""
    import struct, zlib
    try:
        if len(png_bytes) < 100 or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
            return 128.0, 50.0
        pos, width, height, idat = 8, 0, 0, b""
        while pos + 12 <= len(png_bytes):
            n = struct.unpack(">I", png_bytes[pos:pos+4])[0]
            ct = png_bytes[pos+4:pos+8]
            d = png_bytes[pos+8:pos+8+n]
            if ct == b"IHDR" and len(d) >= 8:
                width, height = struct.unpack(">II", d[:8])
            elif ct == b"IDAT":
                idat += d
            elif ct == b"IEND":
                break
            pos += 12 + n
        if not idat or not width:
            return 128.0, 50.0
        raw = zlib.decompress(idat)
        rs = width * 3 + 1
        samp = []
        for i in range(0, min(height, len(raw) // max(rs, 1)), 8):
            row = raw[i*rs+1:i*rs+rs]
            for j in range(0, len(row)-2, 12):
                samp.append(int(0.299*row[j]+0.587*row[j+1]+0.114*row[j+2]))
        if not samp:
            return 128.0, 50.0
        mean = sum(samp) / len(samp)
        std = (sum((x-mean)**2 for x in samp) / len(samp)) ** 0.5
        return mean, std
    except Exception:
        return 128.0, 50.0


def pixel_qa_check(image_bytes: bytes, label: str = "frame") -> dict:
    """
    Instant pixel-level QA on a single PNG frame. No AI required.
    Returns PASS/FAIL with exact numeric sharpness, brightness, std scores.

    Failure thresholds:
      sharpness below 30  -> FAIL (very blurry)
      brightness below 8  -> FAIL (all-black = corrupt VAE decode)
      brightness above 248 -> FAIL (all-white = corrupt)
      std_dev below 5     -> FAIL (flat/uniform = no image content)
    """
    import logging
    sharp = _compute_sharpness(image_bytes)
    mean_b, std_b = _brightness_stats(image_bytes)
    issues = []
    if sharp < 30:
        issues.append("very blurry (sharpness={:.1f}, threshold=30)".format(sharp))
    if mean_b < 8:
        issues.append("all-black corrupt frame (brightness={:.1f})".format(mean_b))
    elif mean_b > 248:
        issues.append("all-white corrupt frame (brightness={:.1f})".format(mean_b))
    if std_b < 5:
        issues.append("flat/uniform frame, no image content (std={:.1f})".format(std_b))
    scores = {"sharpness": round(sharp, 1), "brightness": round(mean_b, 1), "std": round(std_b, 1)}
    logging.info("[PixelQA] {}: {}{}".format(label, scores, " FAIL={}".format(issues) if issues else " PASS"))
    if issues:
        defect = "corrupt_frame" if any(w in issues[0] for w in ["black","white","flat","uniform"]) else "blurry_frame"
        return {"status": "FAIL", "reason": "Pixel QA [{}]: {}".format(label, issues[0]),
                "defect_type": defect, "bounding_box": None, "pixel_scores": scores}
    return {"status": "PASS", "reason": None, "defect_type": None, "bounding_box": None, "pixel_scores": scores}


def check_video_file_sanity(video_path) -> dict:
    """
    File-level sanity check BEFORE opening the video.
    Catches OOM-crashed renders immediately from file size.
    A valid 4-second LTXV clip should be 4-16 MB.
    Below 0.5 MB = VAE decode crashed mid-render.
    """
    import logging
    from pathlib import Path as _Path
    video_path = _Path(video_path)
    if not video_path.exists():
        return {"status": "FAIL", "reason": "File missing: {}".format(video_path.name),
                "defect_type": "missing_file"}
    size_mb = round(video_path.stat().st_size / (1024*1024), 2)
    if size_mb < 0.5:
        return {"status": "FAIL",
                "reason": "File only {}MB — VAE decode crashed (expected 4-16 MB)".format(size_mb),
                "defect_type": "corrupt_file", "size_mb": size_mb}
    logging.info("[FileQA] {}: {}MB OK".format(video_path.name, size_mb))
    return {"status": "PASS", "reason": None, "defect_type": None, "size_mb": size_mb}


# ---------------------------------------------------------------------------
# Moondream — tiny 1.8B vision model, completely free, runs via Ollama locally
# Uses ~1.7 GB disk, ~1.5 GB VRAM (ComfyUI frees VRAM between jobs — no conflict)
# One-time setup:  ollama pull moondream
# ---------------------------------------------------------------------------
OLLAMA_MODEL = "moondream"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_TIMEOUT = 90   # seconds — Moondream on CPU can be slow first run

# ---------------------------------------------------------------------------
# Structured QA Prompt — 7-point checklist aligned with 7 prompt dimensions
# Used when settings.video_qa_structured_mode = True (default)
# Gives Moondream specific targets to look for, making keyword parsing reliable.
# ---------------------------------------------------------------------------
_STRUCTURED_QA_PROMPT = (
    "Look at this image carefully and answer these 7 questions in order. "
    "Be specific and brief for each answer:\n"
    "1. SUBJECT: Is the main subject a girl or woman, or a man or boy? State which."
    "\n2. LOCATION: Is the scene outdoors in nature, or indoors? Describe briefly."
    "\n3. FEET AND LIMBS: Are the subject's feet firmly on the ground? "
    "Or are they floating, sliding, or in an unnatural position?"
    "\n4. FACE CLARITY: Is the subject's face clear and sharp? "
    "Or is it blurry, distorted, melted, or deformed in any way?"
    "\n5. EYE STABILITY: Are the subject's eyes stable, clear, and focused? "
    "Or are they jittery, flickering, or shaking?"
    "\n6. MOTION ARTIFACTS: Is there any visible motion blur, ghosting, "
    "frame tearing, or visual artifact anywhere in the image?"
    "\n7. OVERLAYS: Is there any watermark, text, or logo visible in the image?"
)

# ---------------------------------------------------------------------------
# Open-ended QA Prompt — legacy fallback
# Used when settings.video_qa_structured_mode = False
# ---------------------------------------------------------------------------
_OPEN_ENDED_QA_PROMPT = (
    "Describe everything you see in this image in detail. "
    "Note the gender of the main subject (girl or man/boy), "
    "whether the scene is indoors or outdoors, whether it is raining, "
    "whether an umbrella is present, and look very closely for any visual defects such as "
    "deformed or blurry faces, shaking or jittery eyes, out-of-focus details, "
    "melting shoes, distorted legs or feet, watermarks, or text overlays."
)

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


def _parse_structured_moondream_response(text: str) -> dict[str, Any]:
    """
    Parse Moondream's response to the structured 7-point QA checklist.

    Maps each answer section to a PASS/FAIL determination:
    Q1 (SUBJECT)   -> wrong_subject if male keywords found
    Q2 (LOCATION)  -> wrong_setting if indoors with no outdoor context
    Q3 (FEET)      -> deformed_limbs if floating/sliding detected
    Q4 (FACE)      -> deformed_face if blurry/distorted detected
    Q5 (EYES)      -> instability if jittery/flickering detected
    Q6 (ARTIFACTS) -> artifact if ghosting/tearing detected
    Q7 (OVERLAYS)  -> watermark if text/logo detected
    """
    text_lower = text.lower()

    # Q1: Subject gender check
    # Extract just the answer around "1." or "SUBJECT:"
    subject_section = _extract_section(text_lower, ["1.", "subject:"], next_markers=["2.", "location:"])
    if subject_section:
        male_hits = [w for w in ["man", "boy", "male", "gentleman", "male figure", "businessman"] if w in subject_section]
        female_hits = [w for w in ["girl", "woman", "lady", "female"] if w in subject_section]
        if male_hits and not female_hits:
            return {"status": "FAIL", "reason": f"Subject is male ({male_hits[0]}), expected female",
                    "defect_type": "wrong_subject", "bounding_box": None}

    # Q2: Location check
    location_section = _extract_section(text_lower, ["2.", "location:"], next_markers=["3.", "feet"])
    if location_section:
        indoor_hits = [w for w in ["indoors", "inside", "ceiling", "interior", "room"] if w in location_section]
        outdoor_hits = [w for w in ["outdoor", "outside", "nature", "tree", "sky", "path", "rain", "forest", "park"] if w in location_section]
        if indoor_hits and not outdoor_hits:
            # Only flag if the generation was supposed to be outdoor
            # (soft check — don't fail on indoor scenes that were intended to be indoor)
            pass  # Keep as soft signal, handled by existing _SOFT_FAIL_SIGNALS fallback

    # Q3: Feet and limbs
    feet_section = _extract_section(text_lower, ["3.", "feet"], next_markers=["4.", "face"])
    if feet_section:
        bad_feet = [w for w in ["floating", "sliding", "unnatural", "not on ground", "hovering", "off the ground"] if w in feet_section]
        if bad_feet and not any(ok in feet_section for ok in ["firmly", "on the ground", "planted", "stable", "normal"]):
            return {"status": "FAIL", "reason": f"Feet/limbs problem detected: {bad_feet[0]}",
                    "defect_type": "deformed_limbs", "bounding_box": None}

    # Q4: Face clarity
    face_section = _extract_section(text_lower, ["4.", "face clarity", "face:"], next_markers=["5.", "eye"])
    if face_section:
        bad_face = [w for w in ["blurry", "distorted", "melted", "deformed", "warped", "broken", "unclear"] if w in face_section]
        if bad_face and not any(ok in face_section for ok in ["clear", "sharp", "well-defined", "clean", "no blur"]):
            return {"status": "FAIL", "reason": f"Face defect detected: {bad_face[0]}",
                    "defect_type": "deformed_face", "bounding_box": None}

    # Q5: Eye stability
    eye_section = _extract_section(text_lower, ["5.", "eye stability", "eye:"], next_markers=["6.", "motion", "artifact"])
    if eye_section:
        bad_eyes = [w for w in ["jittery", "flickering", "shaking", "unstable", "blurry"] if w in eye_section]
        if bad_eyes and not any(ok in eye_section for ok in ["stable", "clear", "focused", "sharp", "steady"]):
            return {"status": "FAIL", "reason": f"Eye instability detected: {bad_eyes[0]}",
                    "defect_type": "instability", "bounding_box": None}

    # Q6: Motion artifacts
    artifact_section = _extract_section(text_lower, ["6.", "motion artifact", "artifact"], next_markers=["7.", "overlay", "watermark"])
    if artifact_section:
        bad_artifacts = [w for w in ["ghosting", "tearing", "blur", "artifact", "glitch", "compression"] if w in artifact_section]
        if bad_artifacts and not any(ok in artifact_section for ok in ["no artifact", "none", "no blur", "clean", "no ghosting"]):
            return {"status": "FAIL", "reason": f"Motion artifact detected: {bad_artifacts[0]}",
                    "defect_type": "artifact", "bounding_box": None}

    # Q7: Overlays
    overlay_section = _extract_section(text_lower, ["7.", "overlay", "watermark"], next_markers=[])
    if overlay_section:
        bad_overlays = [w for w in ["watermark", "text", "logo", "overlay", "visible text"] if w in overlay_section]
        if bad_overlays and not any(ok in overlay_section for ok in ["no watermark", "no text", "none", "no logo", "clean"]):
            return {"status": "FAIL", "reason": f"Overlay detected: {bad_overlays[0]}",
                    "defect_type": "watermark", "bounding_box": None}

    # All 7 checks passed
    return {"status": "PASS", "reason": None, "defect_type": None, "bounding_box": None}


def _extract_section(text: str, start_markers: list[str], next_markers: list[str]) -> str:
    """
    Extract the portion of text between a start marker and the next question marker.
    Returns an empty string if no section is found.
    """
    start_idx = -1
    for marker in start_markers:
        idx = text.find(marker)
        if idx != -1:
            start_idx = idx + len(marker)
            break
    if start_idx == -1:
        return ""

    end_idx = len(text)
    for marker in next_markers:
        idx = text.find(marker, start_idx)
        if idx != -1 and idx < end_idx:
            end_idx = idx

    return text[start_idx:end_idx].strip()


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
        # ---- Layer 1: Pixel QA (instant, no AI needed) ----
        # Detects: blurry frames (sharpness), corrupt decodes (black/white/flat frames)
        # Fails immediately without needing Ollama/Moondream to be running.
        pixel_result = pixel_qa_check(image_bytes, label="audit_frame")
        if pixel_result["status"] == "FAIL":
            logging.warning("[QA] Layer 1 Pixel FAIL: %s", pixel_result["reason"])
            return pixel_result

        # ---- Layer 3: Moondream AI QA ----
        # Checks: subject gender, scene, face clarity, eyes, artifacts, overlays
        if not self._is_ollama_alive():
            logging.warning(
                "Ollama offline. Pixel QA passed - defaulting to PASS. "
                "Run 'ollama serve' then 'ollama pull moondream' to enable Moondream QA."
            )
            return {
                "status": "PASS",
                "reason": "Ollama offline - Moondream skipped (Pixel QA passed)",
                "defect_type": None,
                "bounding_box": None,
                "pixel_scores": pixel_result.get("pixel_scores"),
            }

        img_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Choose prompt mode based on settings
        use_structured = True  # default
        if self.settings is not None:
            use_structured = getattr(self.settings, "video_qa_structured_mode", True)

        if use_structured:
            # Structured 7-point checklist — aligned with 7 prompt dimensions
            # More reliable keyword parsing, fewer false positives
            qa_prompt = _STRUCTURED_QA_PROMPT
            response_parser = _parse_structured_moondream_response
            logging.info("[Moondream] Using structured 7-point QA checklist.")
        else:
            # Open-ended description — legacy mode
            qa_prompt = _OPEN_ENDED_QA_PROMPT
            response_parser = _parse_moondream_response
            logging.info("[Moondream] Using open-ended QA description (legacy mode).")

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
                result = response_parser(raw_text)
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
