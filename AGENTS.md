# Agent Instructions — Content Automation Pipeline

## Project Overview
This is a **Streamlit-based AI content automation pipeline** for generating kids' story videos,
LinkedIn posts, YouTube content, and animated 2D story videos.

The project has two repos that work together:
1. **content-automation-pipeline** (this repo) — main Streamlit UI + all content bots
2. **KidsStudio-Orchestrator** (`../KidsStudio-Orchestrator/`) — 2D animated video compiler

## Running the App
```bash
streamlit run app.py
```

## Key Files to Know

### Main Entry Point
- `app.py` — Streamlit UI. All pages/tabs are rendered here. ~3000+ lines.

### Content Bots (`src/content_pipeline/bots/`)
| File | Purpose |
|---|---|
| `image.py` | Image generation — supports OpenAI (`gpt-image-1`), Gemini (`gemini-2.5-flash-image`), Flux (Pollinations). Has 5-attempt retry + placeholder fallback. |
| `audio.py` | TTS audio generation using Gemini TTS with multi-key rotation |
| `gemini_tts.py` | Low-level Gemini TTS wrapper |
| `prompt.py` / `prompt_engine.py` | GPT-based script/caption/hashtag generation |
| `video.py` / `video_engine.py` | Video assembly using FFmpeg |
| `kids_studio_core.py` | Orchestrates the KidsStudio 2D video pipeline |
| `scene_compiler.py` | (in KidsStudio-Orchestrator) Renders animated scenes frame-by-frame + stitches with FFmpeg |
| `linkedin.py` | LinkedIn auto-posting |
| `youtube.py` | YouTube upload via OAuth |
| `google_drive.py` | Auto-backup to Google Drive |

## Environment Variables (`.env`)
All secrets are in `.env` — never commit this file.

### Key Groups
| Keys | Used For |
|---|---|
| `OPENAI_API_KEY` → `OPENAI_API_KEY_4` | GPT text generation + image gen (rotated on 429) |
| `GEMINI_API_KEY` → `GEMINI_API_KEY_7` | Gemini image gen + TTS voice synthesis (slots 1-6 rotate on 429) |
| `GCP_PROJECT_ID`, `IMAGEN_MODEL` | Vertex AI / Imagen 4 image generation |
| `LINKEDIN_*` | LinkedIn OAuth + posting |
| `CANVA_*` | Canva Connect API for thumbnail export |
| `YOUTUBE_CLIENT_SECRETS_FILE` | YouTube Data API OAuth |
| `HF_TOKEN` | HuggingFace gated model downloads (voice cloning) |
| `GOOGLE_DRIVE_FOLDER_ID` | Auto-backup destination |
| `IMAGE_PROVIDER` | Switch between `openai` / `gemini` / `flux` |
| `PROMPT_PROVIDER` | Text provider such as `bedrock_nova`, `openai`, or `anthropic` |

## Git Workflow
- **`main`** — stable/production branch (always push finished work here)
- **`main1`** — active development branch (same code as main currently)
- Delete feature branches older than 48 hours
- Branch naming: `feature/<short-description>`

## KidsStudio 2D Video Pipeline
Located at `../KidsStudio-Orchestrator/`

To compile a story video:
```bash
cd ../KidsStudio-Orchestrator
python src/video_pipeline/scene_compiler.py --manifest projects/moral/scene_manifest.json
```

Output goes to: `projects/<name>/output/<name>_final.mp4`

Assets structure:
```
assets/
  sprites/<character>/
    body.png          # Full character image (transparent bg)
    talk/A.png - X.png  # Lip-sync mouth shapes
  environments/
    <scene>_bg.png    # 1280x720 background images
```

## Common Tasks You'll Be Asked to Do

1. **Fix a bug in the pipeline** — check `app.py` or the relevant bot file
2. **Add a new image provider** — edit `image.py`, add new elif branch, update `.env`
3. **Change voice/TTS settings** — edit `audio.py` or `gemini_tts.py`
4. **Add a new story project** — create `projects/<name>/scene_manifest.json` in KidsStudio-Orchestrator
5. **Push to git** — always push to `main` branch: `git push origin main`
6. **Run video compilation** — use the scene_compiler.py script above

## Important Rules
- Never commit `.env`, `*.mp4`, `scratch/`, `output/`, `__pycache__/`
- Always use `--force-with-lease` not `--force` when force pushing
- The Gemini TTS key pool slots 1-6 (NOT slot 7) — slot 7 is a different key type
- Image sizes: max 2048px, max 5MB (`IMAGE_MAX_DIMENSION`, `IMAGE_MAX_BYTES` in .env)
