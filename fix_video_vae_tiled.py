"""
Fix VAEDecodeTiled nodes in video vs image workflows.

VIDEO workflows (ltxv, svd, wan_i2v): VAEDecodeTiled NEEDS extra fields:
  - tile_size: 512
  - temporal_size: 64   (number of frames per tile)
  - temporal_overlap: 8 (overlap between temporal tiles)
  - overlap: 64         (spatial overlap in pixels)

IMAGE workflows (flux, flux_enhanced, inpaint): should use plain VAEDecode
  because VAEDecodeTiled on still images wastes VRAM and has no benefit.
"""

import json
from pathlib import Path

WORKFLOWS_DIR = Path(r"C:\Users\user\content-automation-pipeline\workflows")

# Video workflows — need full temporal VAEDecodeTiled params
VIDEO_WORKFLOWS = [
    "comfyui_ltxv_i2v_api.json",
    "comfyui_svd_api.json",
    "comfyui_wan_i2v_api.json",
]

# Image workflows — revert to plain VAEDecode (simpler, faster, correct)
IMAGE_WORKFLOWS = [
    "comfyui_flux_api.json",
    "comfyui_flux_api_enhanced.json",
    "comfyui_inpaint_api.json",
]

VIDEO_VAE_TILED_INPUTS_EXTRA = {
    "tile_size": 512,
    "temporal_size": 64,
    "temporal_overlap": 8,
    "overlap": 64,
}


def fix_video_workflow(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for node_id, node in data.items():
        if node.get("class_type") == "VAEDecodeTiled":
            inputs = node["inputs"]
            for k, v in VIDEO_VAE_TILED_INPUTS_EXTRA.items():
                if k not in inputs:
                    inputs[k] = v
                    changed = True
                    print(f"  [{path.name}] Node {node_id}: added {k}={v}")
    if changed:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"  ✅ Saved {path.name}")
    else:
        print(f"  ⏭  {path.name} — already correct, no changes needed")


def fix_image_workflow(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for node_id, node in data.items():
        if node.get("class_type") == "VAEDecodeTiled":
            node["class_type"] = "VAEDecode"
            # VAEDecode only needs: samples + vae — strip extra keys
            node["inputs"] = {
                k: v for k, v in node["inputs"].items()
                if k in ("samples", "vae")
            }
            changed = True
            print(f"  [{path.name}] Node {node_id}: reverted VAEDecodeTiled → VAEDecode")
    if changed:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"  ✅ Saved {path.name}")
    else:
        print(f"  ⏭  {path.name} — already using VAEDecode, no changes needed")


print("=" * 60)
print("Fixing VIDEO workflows (add temporal VAEDecodeTiled params)...")
print("=" * 60)
for wf in VIDEO_WORKFLOWS:
    p = WORKFLOWS_DIR / wf
    if p.exists():
        fix_video_workflow(p)
    else:
        print(f"  ⚠️  Not found: {wf}")

print()
print("=" * 60)
print("Fixing IMAGE workflows (revert to VAEDecode)...")
print("=" * 60)
for wf in IMAGE_WORKFLOWS:
    p = WORKFLOWS_DIR / wf
    if p.exists():
        fix_image_workflow(p)
    else:
        print(f"  ⚠️  Not found: {wf}")

print()
print("Done. All workflows updated.")
