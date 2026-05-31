# Content Automation Pipeline

A staged automation project for creating and distributing daily content to LinkedIn,
YouTube, YouTube Shorts, and Instagram Reels.

The starter implementation covers the first shippable slice:

- Bot 1 produces a validated `prompt.json`.
- Bot 2A produces supporting visual variants for later video/social formats.
- A template renderer produces an exact-text LinkedIn infographic PNG.
- The LinkedIn bot prepares a personal-profile image post payload and receipt without posting publicly.
- All remaining video and publishing stages are mapped in [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

Mock mode is the default, so the pipeline is runnable before paid API access or
social account approvals exist.

## Run It Locally

```bash
cd /Users/lalitprasadsingh/VS_code/content-automation-pipeline
cp .env.example .env
PYTHONPATH=src python3 -m content_pipeline run --date 2026-05-26
```

Generated artifacts appear under:

```text
output/daily/2026-05-26/
  prompt.json
  images/image_square.svg
  images/image_landscape.svg
  images/image_portrait.svg
  images/linkedin_infographic.svg
  images/linkedin_infographic.png
  publish/linkedin_payload.json
  publish/linkedin_receipt.json
  run_manifest.json
```

Run tests without installing packages:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Run The Website

Install the local UI extras and launch the Streamlit front door:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[ui]'
streamlit run app.py
```

For Streamlit Cloud, set the main file path to `streamlit_app.py`.

The app gives you one friendly place to:

- run the daily pipeline,
- open the latest dashboard,
- inspect the unified audio front door,
- preview voice samples when they exist.

## Activate Live Prompt And Images

Create a virtual environment and install optional providers:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[live,dev]'
```

Then update `.env`. OpenAI API access requires an API key; a ChatGPT
subscription alone does not supply API credentials.

```dotenv
PROMPT_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4-mini
OPENAI_IMAGE_MODEL=gpt-image-1

IMAGE_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
GEMINI_API_KEY_2=your_second_gemini_api_key
GEMINI_API_KEY_3=your_third_gemini_api_key
GEMINI_API_KEY_4=your_fourth_gemini_api_key
GEMINI_IMAGE_MODEL=gemini-2.5-flash-image
GEMINI_IMAGE_DAILY_BUDGET=0
GEMINI_IMAGE_MIN_INTERVAL_SECONDS=30
GEMINI_IMAGE_MAX_ATTEMPTS=8
GEMINI_IMAGE_RETRY_BACKOFF_SECONDS=120
IMAGE_FALLBACK_PROVIDER=imagen

# Or use ChatGPT/OpenAI image generation:
# IMAGE_PROVIDER=openai
# OPENAI_IMAGE_MODEL=gpt-image-1

GCP_PROJECT_ID=your_google_cloud_project
GCP_LOCATION=us-central1
IMAGEN_MODEL=imagen-4.0-generate-001
```

Google Application Default Credentials must also be configured for Vertex AI.
LinkedIn remains deliberately non-posting until member OAuth with
`w_member_social` and the media upload flow are wired and tested.

For LinkedIn-only drafting, leave `IMAGE_PROVIDER=mock`: the deterministic
infographic renderer creates the publishable LinkedIn PNG without paid image
generation. When `IMAGE_PROVIDER=gemini`, the provider rotates across the
configured Gemini keys, applies a local cooldown per key, and retries
rate-limited responses instead of hammering a single account. The limiter is
configurable through the Gemini image env vars above.

## Connect Personal LinkedIn Posting

After the LinkedIn app has **Share on LinkedIn** and **Sign In with LinkedIn
using OpenID Connect** enabled, add the public Client ID and private Client
Secret only to local `.env`:

```dotenv
LINKEDIN_CLIENT_ID=your_client_id
LINKEDIN_CLIENT_SECRET=your_client_secret
LINKEDIN_REDIRECT_URI=http://localhost:8080/callback
```

Authorize your profile in the browser. The resulting access token is stored in
the ignored local `.env` file:

```bash
PYTHONPATH=src python3 -m content_pipeline linkedin-auth
```

Preview the generated image post:

```bash
PYTHONPATH=src python3 -m content_pipeline linkedin-post --date 2026-05-26
```

Only after reviewing the preview, publish it to the authorized personal profile:

```bash
PYTHONPATH=src python3 -m content_pipeline linkedin-post --date 2026-05-26 --publish
```

Successful publications write `publish/linkedin_published.json`. A second publish
for the same date is blocked unless `--force-republish` is provided deliberately.
To register an existing post created before this guard was added:

```bash
PYTHONPATH=src python3 -m content_pipeline linkedin-record \
  --date 2026-05-26 --post-id urn:li:share:POST_ID
```

## Render A Video Preview

Phase 2 begins with an exact-text, slide-based landscape preview generated from
the `video_script` section in `prompt.json`. It applies subtle motion and fades
to each branded scene and generates an SRT subtitle sidecar. Install FFmpeg once:

```bash
brew install ffmpeg
```

Then render a local MP4:

```bash
PYTHONPATH=src python3 -m content_pipeline video-preview --date 2026-05-26
```

Output:

```text
output/daily/2026-05-26/video/landscape_preview_16x9.mp4
output/daily/2026-05-26/video/landscape_preview_16x9.srt
```

This silent preview is local-only; it is not uploaded to YouTube.

### Render A 3-5 Minute Video Preview

After generating `prompt.json`, create a fuller narrated YouTube outline and
render a longer silent visual preview with narration stored in the SRT track:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline long-video-preview \
  --date 2026-05-27 --minutes 4
```

Output:

```text
output/daily/2026-05-27/video/longform_script.json
output/daily/2026-05-27/video/longform_preview_16x9.mp4
output/daily/2026-05-27/video/longform_preview_16x9.srt
```

This mode requires the configured OpenAI provider to expand the short daily
topic into 14 to 20 narrated scenes. It does not synthesize voice audio yet.

## Optional Canva Integration

Canva can later supply richer animated templates and MP4 exports, but automated
Brand Template Autofill availability depends on the Canva organization plan.
See [docs/CANVA_SETUP.md](docs/CANVA_SETUP.md) for the current access constraint
and the exact account, template, and brand-kit details needed to wire it in.
The instructional motion-graphics design target is recorded in
[docs/VIDEO_STYLE_REFERENCE.md](docs/VIDEO_STYLE_REFERENCE.md).

## General Story Studio

For non-religious stories, use the generic Story Studio. It supports `kid` and
`adult` audiences, keeps the last 3 story backups in a dashboard dropdown, and
creates OpenArt/Meta AI prompts plus a clip inbox.

Auto-create a 2-5 kids story:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-create \
  --audience kid --date 2026-05-28
```

Create from your own idea:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-create \
  --audience kid --idea "a baby elephant learns to share toys" --date 2026-05-28
```

Create an adult cinematic story:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-create \
  --audience adult --aspect landscape --idea "a queen finds a robot army under the desert"
```

Kids stories mark every scene as `motion_video`. Adult stories use mostly
`2_5d_image` atmospheric scenes, with `motion_video` reserved for action,
discovery or creative movement.

To upload character reference images/videos from the UI, serve the dashboard
locally instead of opening the HTML file directly:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-serve \
  --workspace output/story_studio/episodes/<episode_id>
```

Open `http://127.0.0.1:8765/ui/index.html`. Each character card has an upload
button. Uploaded files are saved to `references/inbox/` and automatically
renamed as `<character_id>_reference.mp4`, `<character_id>_reference.png`, etc.
Use PNG/JPG as the default character reference for consistent faces, colors and
body shape. Use MP4/MOV/WebM only when you want to provide motion style.

After downloading clips into the episode's `clips/inbox/`, assemble:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-assemble \
  --workspace output/story_studio/episodes/<episode_id>
```

### Gemini/Veo Clip Generation

Add your API key only to local `.env`:

```dotenv
GEMINI_API_KEY=your_key_here
GEMINI_VIDEO_MODEL=veo-3.0-fast-generate-001
GEMINI_VIDEO_PRICE_PER_SECOND_USD=0.15
GEMINI_VIDEO_DAILY_CLIP_BUDGET=3
GEMINI_VIDEO_MONTHLY_BUDGET_USD=25
```

Check configuration:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline gemini-config-check
```

Check Gemini image quota state:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline gemini-image-status
```

Generate an image style pack for one topic, a 35-scene storyboard, and a thumbnail prompt:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline image-style-pack \
  --topic "Agile project management" \
  --subject "a team reviewing a glowing workflow board" \
  --output output/image_style_pack.json
```

The daily run also writes a combined dashboard at:

- `output/daily/<date>/daily_dashboard.html`
- `output/daily/<date>/image_style_pack.json`
- `output/daily/<date>/image_storyboard_prompts.json`
- `output/daily/<date>/thumbnail_prompt.txt`
- `output/daily/<date>/voice_profile.json`
- `output/daily/<date>/voice_normalization_preview.txt`
- `output/daily/<date>/indian_voice_samples/voice_samples_manifest.json`
- `output/daily/<date>/voice_status.json`
- `output/daily/<date>/voice_status.html`
- `output/daily/<date>/audio_status.json`
- `output/daily/<date>/audio_status.html`
- `output/daily/<date>/gemini_image_status.html`
- `output/daily/<date>/blocker_status.html`
- `output/daily/<date>/gemini_image_status.json`
- `output/daily/<date>/blocker_journal_snapshot.json`
- `output/daily/<date>/blocker_suggestions.json`

For voice:

- `VOICE_PROVIDER=edge` enables the free Edge TTS Indian voice path for science narration.
- `INDIAN_TTS_VOICE=en-IN-PrabhatNeural` picks the default Indian English narrator.
- `krishna-voice-samples --engine edge` generates the free Indian sample pack.
- `voice-status` prints the current voice provider, selected voice, and whether the daily bundle has real audio or manifest-only metadata.
- `audio-status` summarizes the daily voice bundle plus the latest science and PM audio manifests.
- Install `edge-tts` in your environment if you want to use the free Indian voice path.
- `REFERENCE_AUDIO_DIR` can point the Streamlit Audio tab at a local reference corpus such as the Kaggle Indian Languages Audio Dataset.
- The Streamlit Audio tab now includes a reference audio explorer that can filter and play local Hindi, Hinglish, and other Indian-language sample clips.

Science video workspaces also write:

- `output/science_stories/<story_id>/audio/audio_manifest.json`
- `output/science_stories/<story_id>/audio/audio_status.html`

PM video workspaces also write:

- `output/shorts/<episode_id>/audio/reference/audio_manifest.json`
- `output/shorts/<episode_id>/audio/reference/audio_status.html`
- `output/youtubeVideo/<episode_id>/audio/reference/audio_manifest.json`
- `output/youtubeVideo/<episode_id>/audio/reference/audio_status.html`

Estimate how many full image packages can be generated before starting:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline gemini-image-plan
```

Record or learn a blocker fix from any source:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline blocker-log \
  --stage gemini-image-plan \
  --issue "Gemini quota exhausted" \
  --solution "Add per-key cooldown and fallback routing" \
  --source-title "Google quota guidance" \
  --source-url "https://example.com/rate-limits"

PYTHONPATH=src .venv/bin/python -m content_pipeline blocker-learn \
  --issue "429 Too Many Requests on image generation" \
  --solution "Queue requests and rotate keys before retrying" \
  --source-title "Community note" \
  --source-url "https://example.com/fix"

PYTHONPATH=src .venv/bin/python -m content_pipeline blocker-suggest
PYTHONPATH=src .venv/bin/python -m content_pipeline blocker-status --html
```

Preview the exact Gemini/Veo requests without spending quota:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-gemini-generate \
  --workspace output/story_studio/episodes/<episode_id> --dry-run
```

Generate missing clips while quota is available:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-gemini-generate \
  --workspace output/story_studio/episodes/<episode_id> --limit 1
```

When quota is exhausted, continue manually in Gemini/OpenArt using the same
scene prompts and save files into `clips/inbox/`.

Write a local budget report for the UI:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-budget-report \
  --workspace output/story_studio/episodes/<episode_id>
```

The budget report estimates pending seconds, approximate cost, suggested clips
to auto-generate today, and which clips should fall back to manual generation.

## OpenAI Token Usage

If you want to log the token usage and estimated cost for a single request:

```python
response = openai.chat.completions.create(
    model="gpt-5.4-mini",
    messages=[{"role": "user", "content": "Generate a YouTube script outline."}],
)

usage = response.usage
prompt_tokens = usage.prompt_tokens or 0
completion_tokens = usage.completion_tokens or 0
total_tokens = usage.total_tokens or (prompt_tokens + completion_tokens)

# Replace this with the actual context window for your chosen model.
MODEL_CONTEXT_WINDOW = 128000
remaining_context_tokens = max(MODEL_CONTEXT_WINDOW - total_tokens, 0)

# Example pricing based on your earlier math.
cost = ((prompt_tokens * 0.75) + (completion_tokens * 4.50)) / 1_000_000

print(f"Prompt tokens: {prompt_tokens}")
print(f"Completion tokens: {completion_tokens}")
print(f"Total tokens: {total_tokens}")
print(f"Remaining context tokens: {remaining_context_tokens}")
print(f"Estimated cost: ${cost:.5f}")
```

Important:

- `remaining_context_tokens` is the model context window left in this request.
- Prepaid API credits are not returned by `chat.completions.create`.
- To confirm whether your recent `250` credit purchase landed, check the billing overview in the OpenAI dashboard. OpenAI notes that credit balance updates can take a couple of minutes to appear.

## Architecture

The supplied architecture diagram is kept at [assets/content_automation_pipeline.svg](assets/content_automation_pipeline.svg).
The implementation plan, platform decisions, account checklist, and phase gates
are in [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md). Current official API references
used for integration decisions are listed in [docs/API_REFERENCES.md](docs/API_REFERENCES.md).

## Git

This folder is its own Git repository. Its intended GitHub remote is
`https://github.com/lalit9031/content-automation-pipeline.git`. After creating
an empty repository at that path:

```bash
git push -u origin main
```

The scheduled workflow is configured in `.github/workflows/daily-content.yml`.
It runs safely in mock mode until provider secrets and publishing work are ready.

## LinkedIn App Privacy Policy

Static pages for LinkedIn developer app setup are available in `docs/` and can be
published through GitHub Pages. Configure Pages to deploy from the `main` branch
and `/docs` folder, then use:

```text
https://lalit9031.github.io/content-automation-pipeline/privacy-policy.html
```
