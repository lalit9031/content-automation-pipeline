"""
Step 1: Generate correct reference image using Flux via ComfyUI
Then save it as girl_in_rain_aligned.png for the video pipeline to use.
"""
import sys
import json
import time
import urllib.request
import urllib.parse
import base64
from pathlib import Path

COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_PATH = Path(r"C:\Users\user\Desktop\Output file\image\girl_in_rain_aligned.png")
WORKFLOW_PATH = Path(r"C:\Users\user\content-automation-pipeline\workflows\comfyui_flux_api.json")

PROMPT = (
    "Pixar 3D animated style, cute young girl, approximately 8 years old, "
    "holding a bright red umbrella, walking slowly on a wet cobblestone path "
    "towards a river bank, heavy rain, realistic raindrops, puddle reflections, "
    "detailed face with big expressive eyes, cheerful expression, colorful raincoat, "
    "lush green background, cinematic lighting, highly detailed, sharp focus"
)

def queue_prompt(workflow: dict) -> str:
    data = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(f"{COMFYUI_URL}/prompt", data=data,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
    return result["prompt_id"]

def get_history(prompt_id: str) -> dict:
    with urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}") as r:
        return json.loads(r.read())

def get_image_bytes(filename: str, subfolder: str, folder_type: str) -> bytes:
    params = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": folder_type})
    with urllib.request.urlopen(f"{COMFYUI_URL}/view?{params}") as r:
        return r.read()

def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load the Flux workflow
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))

    # Inject prompt only into node 6 (positive CLIPTextEncode)
    # Node 6 = positive, Node 7 = negative — confirmed from workflow structure
    POSITIVE_NODE = "6"
    for node_id, node in workflow.items():
        inp = node.get("inputs", {})
        if node_id == POSITIVE_NODE and "text" in inp:
            inp["text"] = PROMPT
            print(f"  Set positive prompt on node {node_id}")
        # Set resolution: 768x1024 portrait (better for a person)
        if "width" in inp and "height" in inp:
            inp["width"] = 768
            inp["height"] = 1024
            print(f"  Set resolution 768x1024 on node {node_id}")

    print(f"\nQueueing Flux image generation...")
    print(f"Prompt: {PROMPT[:80]}...")
    prompt_id = queue_prompt(workflow)
    print(f"Prompt ID: {prompt_id}")

    # Wait for completion
    print("Waiting for render to complete", end="", flush=True)
    for _ in range(300):  # max 5 minutes
        time.sleep(2)
        history = get_history(prompt_id)
        if prompt_id in history:
            outputs = history[prompt_id].get("outputs", {})
            for node_id, node_output in outputs.items():
                for key in ("images",):
                    if key in node_output:
                        for img_info in node_output[key]:
                            fname = img_info["filename"]
                            subfolder = img_info.get("subfolder", "")
                            ftype = img_info.get("type", "output")
                            print(f"\nImage ready: {fname}")
                            img_bytes = get_image_bytes(fname, subfolder, ftype)
                            OUTPUT_PATH.write_bytes(img_bytes)
                            print(f"Saved to: {OUTPUT_PATH}")
                            return
        print(".", end="", flush=True)

    print("\nERROR: Timed out waiting for image generation.")

if __name__ == "__main__":
    main()
