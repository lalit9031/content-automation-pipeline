# 🎬 AI Video Generation Pipeline — Complete Documentation

> **Local, free, crash-safe AI pipeline for generating animated children's videos.**
> Runs entirely on your machine using ComfyUI + Flux + LTXV + Moondream.
> No subscriptions. No API keys. No cloud costs.

---

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Hardware & Requirements](#hardware--requirements)
3. [Architecture Diagram](#architecture-diagram)
4. [Component Reference](#component-reference)
5. [Running the Pipeline](#running-the-pipeline)
6. [VS Code Integration](#vs-code-integration)
7. [Visual QA with Moondream](#visual-qa-with-moondream)
8. [RAM & VRAM Management](#ram--vram-management)
9. [System Safety Fixes](#system-safety-fixes)
10. [Workflow Files Reference](#workflow-files-reference)
11. [Troubleshooting](#troubleshooting)
12. [Upgrade Path](#upgrade-path)

---

## System Overview

The pipeline generates animated children's videos in 3 sequential stages:

```
Stage 1: IMAGE         Stage 2: VIDEO              Stage 3: QA
──────────────         ──────────────              ──────────
Flux 1-Dev fp8   →    LTXV 13B fp8          →    Moondream 1.8B
(ComfyUI)              (ComfyUI)                    (Ollama)
768×1024 image         768×512 @ 25 FPS             Frame-by-frame
~30 seconds            ~3–4 minutes                 visual check
                        ↓ if FAIL: retry up to 3×
```

**Output location:** `C:\Users\user\Desktop\Output file\`
- Images → `image\`
- Videos → `video\`

---

## Hardware & Requirements

| Component | Your Setup | Minimum |
|-----------|-----------|---------|
| GPU | AMD RX 7900 XTX (24 GB VRAM) | 8 GB VRAM |
| RAM | 32 GB DDR5 4800 MHz | 16 GB |
| OS | Windows 11 | Windows 10 |
| Python | 3.11+ | 3.10+ |
| ComfyUI | 0.25.1+ | 0.20+ |
| Ollama | 0.30+ | 0.25+ |

### Recommended RAM Upgrade
Adding a second 32 GB DDR5 4800 MHz stick (total 64 GB) unlocks:
- procgov cap: 25 GB → 50 GB
- Resolution: 768×512 → 1280×720 HD
- Video length: 97 frames → 200+ frames
- More stable model offloading via `--lowvram`

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI VIDEO PIPELINE                             │
│                                                                 │
│  generate_reference_image.py          generate_video_request.py │
│          │                                      │               │
│          ▼                                      ▼               │
│  ┌──────────────┐                   ┌────────────────────────┐  │
│  │  ComfyUI     │                   │  VideoAgentOrchestrator│  │
│  │  Flux 1-Dev  │                   │  ┌──────────────────┐  │  │
│  │  fp8         │                   │  │ Developer Agent  │  │  │
│  │  768×1024    │                   │  │ (sets params)    │  │  │
│  └──────┬───────┘                   │  └────────┬─────────┘  │  │
│         │ girl_in_rain_aligned.png   │           ▼            │  │
│         └──────────────────────────▶│  ┌──────────────────┐  │  │
│                                      │  │  ComfyUI         │  │  │
│                                      │  │  LTXV 13B fp8    │  │  │
│  procgov (25 GB RAM cap) ────────────│  │  768×512 video   │  │  │
│  --lowvram ──────────────────────────│  └────────┬─────────┘  │  │
│  --fp8_e4m3fn-unet ──────────────────│           │            │  │
│                                      │           ▼            │  │
│                                      │  ┌──────────────────┐  │  │
│  Ollama (port 11434) ────────────────│  │  Tester Agent    │  │  │
│  Moondream 1.8B ────────────────────▶│  │  Moondream QA    │  │  │
│                                      │  │  5 frame checks  │  │  │
│                                      │  └────────┬─────────┘  │  │
│                                      │           │            │  │
│                                      │    PASS ──┘  FAIL ──┐  │  │
│                                      │                      │  │  │
│                                      │   Output MP4         │  │  │
│                                      │   (Desktop\Output)   ▼  │  │
│                                      │              retry (max 3)│  │
│                                      └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Reference

### 1. Image Generation — `generate_reference_image.py`
Generates the reference image used as the first frame for video generation.

| Setting | Value |
|---------|-------|
| Model | `flux1-dev-fp8.safetensors` |
| Resolution | 768 × 1024 (portrait) |
| Workflow | `workflows/comfyui_flux_api.json` |
| Output | `Desktop\Output file\image\girl_in_rain_aligned.png` |

```bash
python generate_reference_image.py
```

### 2. Video Generation — `generate_video_request.py`
Runs the full multi-agent video generation + QA loop.

| Setting | Value |
|---------|-------|
| Model | `ltxv-13b-0.9.8-dev-fp8.safetensors` |
| Resolution | 768 × 512 |
| FPS | 5 → interpolated to 25 via ffmpeg |
| Frames | 97 |
| Duration | ~4–5 seconds |
| Max retries | 3 |
| Workflow | `workflows/comfyui_ltxv_i2v_api.json` |
| Output | `Desktop\Output file\video\girl_walking_to_river.mp4` |

```bash
python generate_video_request.py
```

### 3. Visual QA — Moondream via Ollama

| Setting | Value |
|---------|-------|
| Model | `moondream:latest` (1.8B) |
| Download size | 1.7 GB |
| VRAM used | ~1.5 GB |
| Port | 11434 |
| Frames checked | 5 per video |
| Source | `src/content_pipeline/bots/qa_auditor.py` |

---

## Running the Pipeline

### Option A — Full Pipeline (Recommended)
```bash
# Step 1: Start ComfyUI (in a separate terminal)
cd C:\ComfyUI
procgov.exe --maxmem 25G -- python_embeded\python.exe -s ComfyUI\main.py ^
    --windows-standalone-build --enable-dynamic-vram ^
    --lowvram --fp8_e4m3fn-unet --fp8_e4m3fn-text-enc

# Step 2: Start Ollama (in another terminal)
ollama serve

# Step 3: Generate reference image
python generate_reference_image.py

# Step 4: Generate video with QA
python generate_video_request.py
```

### Option B — VS Code (Easiest)
Press `Ctrl+Shift+P` → **Tasks: Run Task** → select from the menu:
- `🚀 Start ComfyUI (25GB RAM cap)`
- `🧠 Start Ollama (Moondream QA)`
- `🎨 Generate Reference Image (Flux)`
- `🎬 Generate Video (LTXV 13B + QA)`
- `🔄 Full Pipeline (Image → Video → QA)`

---

## VS Code Integration

### Available Tasks (`Ctrl+Shift+P` → Tasks: Run Task)

| Task | What It Does |
|------|-------------|
| `🚀 Start ComfyUI` | Starts ComfyUI with 25GB RAM cap and low VRAM flags |
| `🧠 Start Ollama` | Starts the Ollama server for Moondream QA |
| `🎨 Generate Reference Image` | Generates the girl-in-rain reference image via Flux |
| `🎬 Generate Video` | Full video generation + Moondream QA loop |
| `🔍 QA Test — Default` | Tests default image and video through Moondream |
| `🔍 QA Test — Custom Image` | Prompts for image path + prompt, then tests |
| `🔍 QA Test — Custom Video` | Prompts for video path + prompt, then tests |
| `🔄 Full Pipeline` | Runs image then video sequentially |

### Running QA Test from VS Code Terminal
```bash
# Test default image and video
python test_visual_qa.py

# Test a specific image
python test_visual_qa.py --image "C:\path\to\image.png" --prompt "your prompt"

# Test a specific video (5 frame samples)
python test_visual_qa.py --video "C:\path\to\video.mp4" --prompt "your prompt"

# Test video with more samples
python test_visual_qa.py --video "C:\path\to\video.mp4" --samples 10
```

---

## Visual QA with Moondream

### How It Works

Moondream describes each video frame in plain English. Our smart parser
then detects PASS or FAIL using keyword matching:

```
Frame → Moondream describes → Parser reads keywords → PASS or FAIL
```

**FAIL triggers (any one detected = FAIL):**

| Keyword Detected | Defect Type |
|-----------------|-------------|
| "man in", "male", "businessman" | wrong_subject |
| "indoor", "shopping mall", "ceiling" | wrong_setting |
| "watermark", "logo", "text overlay" | watermark |
| "melted", "deformed face" | deformed_face |
| "missing eye", "extra finger" | extra_limb |

**PASS requires:** 2+ of these detected:
`girl, young girl, rain, umbrella, outdoor, river, puddle, no defects`

### One-Time Setup
```bash
# Install Ollama (if not installed)
winget install Ollama.Ollama

# Pull Moondream model (~1.7 GB download)
ollama pull moondream

# Verify it works
python test_visual_qa.py
```

---

## RAM & VRAM Management

### Safety Layers

```
Layer 1: procgov --maxmem 25G
         Hard RAM cap. If ComfyUI tries to use >25 GB, Windows blocks it.
         Free space for Windows: ~7 GB

Layer 2: --lowvram flag
         ComfyUI loads one model at a time, offloads to RAM between steps.
         Without this: 19 GB VRAM at once → crash.
         With this: ~12-14 GB peak VRAM.

Layer 3: --fp8_e4m3fn-unet + --fp8_e4m3fn-text-enc
         Compresses model weights from float32 → 8-bit.
         Cuts VRAM from ~24 GB → ~14 GB for LTXV 13B.

Layer 4: PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:256
         Splits large GPU memory allocations into 256 MB chunks.
         Prevents "can't allocate X GB contiguous block" errors.

Layer 5: VAEDecodeTiled (video workflows)
         Decodes video in tiles instead of all at once.
         Prevents VRAM spike during final frame reconstruction.
```

### Model VRAM Usage
| Model | VRAM (fp8) | VRAM (fp32) |
|-------|------------|-------------|
| LTXV 13B | ~12.4 GB | ~24+ GB |
| VideoVAE | ~2.4 GB | ~4.8 GB |
| MochiTE text encoder | ~4.5 GB | ~9 GB |
| Flux 1-Dev | ~8 GB | ~16 GB |
| **Peak total (LTXV)** | **~14 GB** | **>37 GB** |

---

## System Safety Fixes

Three Windows registry fixes applied via `apply_system_fixes_RUN_AS_ADMIN.bat`:

| Fix | Registry Key | Default | New Value | Effect |
|-----|-------------|---------|-----------|--------|
| GPU TDR timeout | `TdrDelay` | 2 sec | **30 sec** | Screen stays on during model loading |
| GPU DDI timeout | `TdrDdiDelay` | 5 sec | **30 sec** | Display driver doesn't panic-reset |
| TCP socket recycle | `TcpTimedWaitDelay` | 120 sec | **30 sec** | Fixes WinError 10055 socket exhaustion |

**To reapply after a format/reinstall:**
```bash
# Right-click → Run as Administrator
apply_system_fixes_RUN_AS_ADMIN.bat
```

---

## Workflow Files Reference

All ComfyUI workflows are in `workflows/`:

| File | Type | Model | Resolution | VAE Node |
|------|------|-------|------------|----------|
| `comfyui_flux_api.json` | Image | Flux 1-Dev fp8 | 1024×1024 | VAEDecode |
| `comfyui_flux_api_enhanced.json` | Image | Flux 1-Dev fp8 | 1024×1024 | VAEDecode |
| `comfyui_inpaint_api.json` | Inpaint | Flux 1-Dev fp8 | variable | VAEDecode |
| `comfyui_ltxv_i2v_api.json` | Video | LTXV 13B fp8 | 768×512 | VAEDecodeTiled* |
| `comfyui_svd_api.json` | Video | SVD XT | 1024×576 | VAEDecodeTiled* |
| `comfyui_wan_i2v_api.json` | Video | WAN 2.1 | 512×512 | VAEDecodeTiled* |

> *Video `VAEDecodeTiled` requires: `tile_size=512`, `temporal_size=64`,
> `temporal_overlap=8`, `overlap=64`

---

## Troubleshooting

### Screen went black during generation
**Cause:** GPU TDR timeout (2s default) fired during model loading.
**Fix:** Apply `apply_system_fixes_RUN_AS_ADMIN.bat` and reboot.

### WinError 10055 — socket buffer full
**Cause:** Old TCP connections from previous ComfyUI sessions not released.
**Fix:**
1. Kill all python processes: `Stop-Process -Name python -Force`
2. Wait 30 seconds for socket recycle (after registry fix)
3. Restart ComfyUI

### Video shows wrong subject (man instead of girl)
**Cause:** Reference image `girl_in_rain_aligned.png` was corrupted/wrong.
**Fix:** Regenerate the reference image first:
```bash
python generate_reference_image.py
```

### ComfyUI — VAEDecodeTiled missing inputs error
**Cause:** Video workflow was missing `temporal_size`, `temporal_overlap`, `overlap`.
**Fix:** Run the repair script:
```bash
python fix_video_vae_tiled.py
```

### Moondream not responding
**Fix:**
```bash
# Check Ollama is running
ollama list

# If not running
ollama serve

# If moondream not installed
ollama pull moondream

# Test it
python test_visual_qa.py
```

### Flux 400 Bad Request error
**Cause:** Wrong model filename in workflow JSON.
**Fix:** Model must be `flux1-dev-fp8.safetensors` (not `flux1-dev.safetensors`).
Already corrected in both Flux workflow files.

---

## Upgrade Path

### After Adding 32 GB RAM (Total 64 GB)

Update `procgov` cap and resolution in these files:

**1. `run_with_comfyui.py` and `comfy_client.py`:**
```python
# Change:
"--maxmem", "25G"
# To:
"--maxmem", "50G"
```

**2. `comfyui_ltxv_i2v_api.json` — raise resolution:**
```json
// Node 77 LTXVImgToVideo:
"width": 1280,
"height": 720,
"length": 65
```

**3. `generate_video_request.py`:**
```python
size="1280x720",  # was "768x512"
```

**4. `generate_reference_image.py`:**
```python
wf['5']['inputs']['width'] = 1280
wf['5']['inputs']['height'] = 720
```

**Expected result after upgrade:**
- Resolution: 768×512 → **1280×720 (HD)**
- Stability: much better (50 GB offload buffer)
- Crash risk: near zero

---

*Last updated: June 2026*
*Pipeline version: 2.0 — Local GPU Edition*
