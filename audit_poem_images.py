"""
audit_poem_images.py
====================
Runs automated visual QA on all 6 generated poem images.
Uses pixel-level check (sharpness/brightness/std) and Moondream via Ollama.
"""

import sys
import json
import base64
import urllib.request
import urllib.error
from pathlib import Path

# Add src folder to PYTHONPATH
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from content_pipeline.bots.qa_auditor import pixel_qa_check

OUTPUT_DIR = Path(r"C:\Users\user\Desktop\Output file\poem_images")
ARTIFACT_DIR = Path(r"C:\Users\user\.gemini\antigravity\brain\c4a48922-6575-4171-a650-44b055247dc0")
OLLAMA_URL = "http://localhost:11434"

SCENE_PROMPTS = {
    1: {
        "title": "Ring_a_Ring_Gathering",
        "file": "scene_01_Ring_a_Ring_Gathering.png",
        "description": "4 children standing in a sunny garden smiling and reaching out.",
        "qa_question": "Does this image show 4 cartoon children standing in a garden reaching toward each other? Are their faces clear and free of deformities? Is there any text or watermark?"
    },
    2: {
        "title": "Pocket_Full_of_Posies",
        "file": "scene_02_Pocket_Full_of_Posies.png",
        "description": "4 children holding hands in a circle in a flower garden, holding flowers.",
        "qa_question": "Does this image show 4 cartoon children holding hands in a circle in a flower garden? Are they holding flowers? Are their faces and limbs clear?"
    },
    3: {
        "title": "Atishoo_Spinning_Fast",
        "file": "scene_03_Atishoo_Spinning_Fast.png",
        "description": "4 children spinning fast in a circle, laughing/sneezing, dresses flaring.",
        "qa_question": "Does this image show 4 cartoon children spinning fast in a circle holding hands? Are their faces clear? Is there any blur or motion lines?"
    },
    4: {
        "title": "We_All_Fall_Down",
        "file": "scene_04_We_All_Fall_Down.png",
        "description": "4 children falling down onto the green grass, laughing.",
        "qa_question": "Does this image show 4 cartoon children falling down onto the grass? Are they laughing/smiling? Are there any weird extra limbs or face distortions?"
    },
    5: {
        "title": "Getting_Up_Laughing",
        "file": "scene_05_Getting_Up_Laughing.png",
        "description": "4 children getting up from the grass, helping each other, laughing.",
        "qa_question": "Does this image show 4 cartoon children getting up from the grass and helping each other? Are their faces clear? Any visual glitches?"
    },
    6: {
        "title": "Ring_Forms_Again",
        "file": "scene_06_Ring_Forms_Again.png",
        "description": "4 children holding hands in a ring again, smiling warmly.",
        "qa_question": "Does this image show 4 cartoon children holding hands in a circle again in a garden? Are their expressions happy and faces clear?"
    }
}

def ask_moondream(img_bytes: bytes, question: str) -> str:
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    payload = {
        "model": "moondream",
        "prompt": question,
        "images": [img_b64],
        "stream": False
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as res:
            response = json.loads(res.read().decode("utf-8"))
            return response.get("response", "").strip()
    except Exception as e:
        return f"Moondream error: {e}"

def main():
    print("Starting Poem Image QA Audit...")
    report_lines = [
        "# Ring-a-Ring O'Roses Poem Images QA Audit Report",
        "",
        "This report contains the automated QA analysis of all 6 poem scene images generated for the Ring-a-Ring O'Roses animation pipeline.",
        "Each image has been analyzed for pixel-level quality (sharpness, VAE decode sanity) and content compliance using Moondream VLM.",
        "",
        "## Overall Summary Table",
        "",
        "| Scene | Filename | Size | Sharpness | Brightness | std | Moondream QA Status |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    
    detailed_sections = []
    
    for num, info in SCENE_PROMPTS.items():
        img_path = OUTPUT_DIR / info["file"]
        if not img_path.exists():
            print(f"File not found: {img_path}")
            report_lines.append(f"| {num} | {info['file']} | **MISSING** | - | - | - | - |")
            continue
            
        img_bytes = img_path.read_bytes()
        size_kb = len(img_bytes) / 1024
        
        # 1. Pixel QA
        p_res = pixel_qa_check(img_bytes, label=f"Scene {num}")
        scores = p_res.get("pixel_scores", {})
        sharp = scores.get("sharpness", 0.0)
        bright = scores.get("brightness", 0.0)
        std = scores.get("std", 0.0)
        
        # 2. Content QA via Moondream
        print(f"Auditing Scene {num} via Moondream...")
        md_desc = ask_moondream(img_bytes, "Describe what is shown in this image, including the number of children, their actions, the background, and if there is any blur or text.")
        md_qa = ask_moondream(img_bytes, info["qa_question"])
        
        # Copy to artifacts directory for user viewing
        dest_path = ARTIFACT_DIR / f"s{num}.png"
        dest_path.write_bytes(img_bytes)
        
        # Check pass status
        status = "PASS"
        status_icon = "🟢 PASS"
        
        # Simple rule checks on Moondream responses
        fail_reasons = []
        md_qa_lower = md_qa.lower()
        if "not show" in md_qa_lower or "no, " in md_qa_lower or "does not show" in md_qa_lower or "fail" in md_qa_lower or "not have 4" in md_qa_lower or "unclear" in md_qa_lower:
            fail_reasons.append("Moondream content mismatch warning")
            status_icon = "🟡 REVIEW"
            status = "REVIEW"
            
        if p_res["status"] == "FAIL":
            fail_reasons.append(p_res["reason"])
            status_icon = "🔴 FAIL"
            status = "FAIL"
            
        report_lines.append(
            f"| {num} | [{info['file']}](file:///{img_path.as_posix()}) | {size_kb:.1f} KB | {sharp} | {bright} | {std} | {status_icon} |"
        )
        
        detailed_sections.append(f"""
### Scene {num}: {info['title'].replace('_', ' ')}
* **Image File**: [{info['file']}](file:///{img_path.as_posix()})
* **Artifact Copy**: [s{num}.png](file:///{dest_path.as_posix()})
* **Prompt Intent**: {info['description']}
* **Size**: {size_kb:.1f} KB
* **Pixel QA Scores**: Sharpness: **{sharp}** (Threshold >= 30), Brightness: **{bright}** (Threshold 8-248), Std Dev: **{std}** (Threshold >= 5)
* **Pixel QA Result**: **{p_res['status']}** {f'({p_res.get("reason")})' if p_res.get('reason') else ''}
* **Moondream Description**:
  > {md_desc}
* **Moondream QA Checklist Response**:
  > {md_qa}
* **QA Status**: **{status_icon}** {f'({", ".join(fail_reasons)})' if fail_reasons else ''}

![Scene {num} Preview](file:///{dest_path.as_posix()})

---""")

    # Assemble and write the markdown report
    report_content = "\n".join(report_lines) + "\n\n## Detailed Scene Audits\n" + "\n".join(detailed_sections)
    
    report_file = ARTIFACT_DIR / "poem_images_qa_report.md"
    report_file.write_text(report_content, encoding="utf-8")
    print(f"Report written to: {report_file}")

if __name__ == "__main__":
    main()
