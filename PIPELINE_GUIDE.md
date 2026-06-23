# 🎬 Content Automation Pipeline — VS Code Run Guide

## ✅ Quick Start (Run in VS Code Terminal)

```bash
# 1. Open the project folder in VS Code
# File > Open Folder > C:\Users\user\content-automation-pipeline

# 2. Open terminal in VS Code (Ctrl + `)

# 3. Run the pipeline
python generate_longform_video.py
```

**Output will appear at:** `C:\Users\user\Desktop\Output file\`

---

## 📋 Prerequisites Checklist

Before running, verify these are ready:

| Item | How to Check | Fix if Missing |
|---|---|---|
| ComfyUI installed | `Test-Path C:\ComfyUI\ComfyUI\main.py` | Install ComfyUI to `C:\ComfyUI` |
| LTXV model present | `Test-Path "C:\ComfyUI\ComfyUI\models\checkpoints\ltxv-13b-0.9.8-dev-fp8.safetensors"` | Download LTXV FP8 model |
| T5 text encoder | `Test-Path "C:\ComfyUI\ComfyUI\models\clip\t5xxl_fp8_e4m3fn.safetensors"` | Download T5-XXL FP8 |
| Python packages | `python -c "import content_pipeline"` | Run `pip install -e .` from project root |
| .env file exists | `Test-Path .env` | Copy `.env.example` to `.env` |

---

## 🎮 How to Change the Prompt

Open `generate_longform_video.py` and edit line 28:

```python
RAW_PROMPT = "girl walking in rain forest toward a river"
#              ↑ Change this to anything you want
```

**Examples:**
```python
RAW_PROMPT = "woman walking on a beach at sunset"
RAW_PROMPT = "man running through a forest"
RAW_PROMPT = "girl standing in a park on a sunny day"
```

---

## ⚙️ Current Quality Settings (64GB RAM Optimized)

| Setting | Value | File |
|---|---|---|
| Resolution | **768×512** | `workflows/comfyui_ltxv_i2v_api.json` |
| Sampling steps | **45** | `workflows/comfyui_ltxv_i2v_api.json` |
| CFG scale | **3.5** | `workflows/comfyui_ltxv_i2v_api.json` |
| Max frames per clip | **121** (~5s) | `src/.../motion.py` |
| Clip duration | **5s** per scene | `src/.../script_engine.py` |
| RAM cap (procgov) | **48GB** | `src/.../comfy_client.py` |
| Camera framing | **Medium shot, face visible** | `src/.../prompt_expander.py` |

---

## 🧠 Pipeline Architecture (What Happens Step by Step)

```
generate_longform_video.py
        │
        ▼
LongFormOrchestrator.run()
        │
        ├─[Step 1] SmartPromptExpander
        │   └─ "girl walking in rain" → 7-dimension structured prompt
        │       • Subject, Clothing, Expression
        │       • Scene, Environment, Lighting
        │       • Motion, Camera, Quality
        │
        ├─[Step 2] ScriptEngine
        │   └─ Splits target duration into scenes (5s each)
        │       • 6s → 1 clip
        │       • 30s → 6 clips (with narrative arc)
        │
        ├─[Step 3] Flux Image Generation (via ComfyUI)
        │   └─ Generates source PNG image for Scene 1
        │
        ├─[RAM Checkpoint] ComfyUI restarts
        │   └─ Flushes Flux (~11GB VRAM) before loading LTXV
        │       ★ This is why sampling is fast & RAM stays controlled
        │
        ├─[Step 4] For each scene:
        │   ├─ LTXV Video Generation (via ComfyUI)
        │   │   └─ 45 steps @ 768×512 → 97-121 frames
        │   ├─ Smart QA Audit (pixel-level + Moondream)
        │   │   ├─ File size check (corrupt = < 1MB)
        │   │   ├─ Sharpness score (Laplacian variance)
        │   │   ├─ Face visibility check
        │   │   ├─ Frozen frame detection
        │   │   └─ Moondream visual AI check
        │   └─ Last frame extraction → start of next clip
        │
        └─[Step 5] VideoAssembler
            └─ Stitches all clips → final .mp4
```

---

## 📁 Output Folder Structure

```
C:\Users\user\Desktop\Output file\
├── test_single_clip\
│   ├── scene_01_source_image.png   ← Generated Flux image
│   ├── clips\
│   │   └── clip_01.mp4             ← Raw clip
│   ├── frames\
│   │   └── clip_01_last_frame.png  ← For chaining
│   └── test_single_clip_final.mp4  ← ✅ FINAL VIDEO
│
└── test_30s_video\
    ├── scene_01_source_image.png
    ├── clips\
    │   ├── clip_01.mp4 ... clip_06.mp4
    ├── frames\
    │   └── clip_01_last_frame.png ... 
    └── test_30s_video_final.mp4    ← ✅ FINAL VIDEO (30 seconds)
```

---

## 🔍 Smart QA — What It Checks Automatically

The QA system now runs **3 layers of checks** on every clip:

### Layer 1: Pixel-Level (No AI needed, instant)
| Check | What it detects | Threshold |
|---|---|---|
| **File size** | Corrupt/truncated render | < 1 MB = FAIL |
| **Sharpness score** | Blurry frames | Laplacian variance < 50 = FAIL |
| **Face presence** | No face visible in frame | Dark/flat frame = FAIL |
| **Frozen frames** | Stuck/static video | > 30% frozen = FAIL |
| **Color uniformity** | All-black/all-grey corrupt frames | Std deviation < 5 = FAIL |

### Layer 2: Temporal (Video-level)
| Check | What it detects |
|---|---|
| Consecutive frozen frames | Decode failure |
| Last-second freeze ratio | Clip cut off early |

### Layer 3: Moondream Vision AI (when Ollama running)
| Check | Question asked |
|---|---|
| Subject correct | Girl/woman or man/boy? |
| Scene correct | Outdoors or indoors? |
| Feet/limbs | Floating, sliding? |
| Face clarity | Sharp or blurry/deformed? |
| Eye stability | Jittery or stable? |
| Motion artifacts | Ghosting, tearing? |
| Overlays | Watermarks, text? |

> **To enable Moondream QA:**
> ```bash
> ollama serve        # In one terminal
> ollama pull moondream   # One-time download
> ```

---

## 🚨 Common Issues & Fixes

| Symptom | Cause | Fix |
|---|---|---|
| `ComfyUI not responding` | ComfyUI failed to start | Check `comfyui_server_runtime.log` |
| `Failed to start ComfyUI` | Port 8188 already in use | Kill old ComfyUI: `Stop-Process -Name python -Force` |
| `Model not found` | Wrong model path | Verify model files in `C:\ComfyUI\ComfyUI\models\` |
| Blurry video | Steps too low / OOM crash | Check RAM, confirm steps=45 in workflow JSON |
| No face visible | Wide shot framing | Already fixed — medium shot is default now |
| Broken/corrupt video | OOM during VAE decode | 64GB RAM fix applied — should not occur |
| Very slow (>30min/clip) | Too many frames or old settings | Verify 121 frame cap in `motion.py` |

---

## 🔧 Key Files Reference

| File | Purpose |
|---|---|
| `generate_longform_video.py` | **START HERE** — main entry point |
| `.env` | API keys, output paths, feature flags |
| `workflows/comfyui_ltxv_i2v_api.json` | Steps, CFG, resolution, VAE tile settings |
| `src/.../prompt_expander.py` | Camera framing, quality prompts, negative anchors |
| `src/.../script_engine.py` | Clip duration, narrative arc |
| `src/.../motion.py` | Frame count cap (MAX_LTXV_FRAMES) |
| `src/.../comfy_client.py` | RAM cap, ComfyUI startup flags |
| `src/.../long_form_orchestrator.py` | Pipeline flow, phase restart logic |
| `src/.../qa_auditor.py` | Smart QA — all quality checks |
| `comfyui_server_runtime.log` | ComfyUI live log — check if stuck |

---

## 💡 Tips for Best Results

1. **Close Chrome/heavy apps** before running — even with 64GB RAM, fewer competing processes = faster
2. **Don't touch the PC** during VAE decode — moving windows can cause GPU context switches
3. **Check the log** if stuck: open `comfyui_server_runtime.log` and look for progress `██ 30/45`
4. **Videos on Desktop** — all outputs save to `C:\Users\user\Desktop\Output file\` automatically
5. **To change prompt only**: edit `RAW_PROMPT` in `generate_longform_video.py` — no other changes needed

---

## 📊 Expected Timing (64GB RAM)

| Stage | Time |
|---|---|
| ComfyUI startup | ~45 seconds |
| Flux image generation | ~30 seconds |
| ComfyUI restart (phase switch) | ~20 seconds |
| LTXV sampling (45 steps) | ~3–4 minutes |
| VAE decode (121 frames) | ~5–8 minutes |
| **Per clip total** | **~9–13 minutes** |
| **30-second video (6 clips)** | **~55–75 minutes** |
