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

IMAGE_PROVIDER=imagen
GCP_PROJECT_ID=your_google_cloud_project
GCP_LOCATION=us-central1
IMAGEN_MODEL=imagen-4.0-generate-001
```

Google Application Default Credentials must also be configured for Vertex AI.
LinkedIn remains deliberately non-posting until member OAuth with
`w_member_social` and the media upload flow are wired and tested.

For LinkedIn-only drafting, leave `IMAGE_PROVIDER=mock`: the deterministic
infographic renderer creates the publishable LinkedIn PNG without paid Imagen
generation. Enable Imagen only when supporting visual variants are needed. Run
manifests identify active providers and report `mode: live` whenever OpenAI or
Imagen is enabled.

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

## Bal Krishna Motion Validation Agent

An experimental children's-story workflow now generates authentic Hindi voice
samples, plans short real-motion environmental validation clips with Sora,
assembles approved clips, and blocks YouTube upload until a dated policy report
passes. The desired child-character motion plan is retained for provider review
after a live character request was rejected by moderation; it never sends
family face photos as motion-video reference images.

See [docs/KRISHNA_AGENT_WORKFLOW.md](docs/KRISHNA_AGENT_WORKFLOW.md) for the
one-agent-per-job design and safe voice-source policy, and
[docs/KRISHNA_MOTION_AGENT.md](docs/KRISHNA_MOTION_AGENT.md) for motion,
provider-boundary, character-identity verification, policy-check and
private-upload commands. The pilot narration selection is recorded as the
built-in `marin` sample; character clips require a provider route that permits
original fictional human-like characters. A gated Luma evaluation route can
generate fictional identity stills and, after creator approval, one private
five-second Kanha motion test. For the pilot, a no-subscription local 2.5D
route renders moving vertical shots from the approved fictional artwork.

For daily OpenArt or Meta AI assisted production, generate a local episode UI:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-daily-video-ui \
  --date 2026-05-28
```

For a landscape YouTube version:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-daily-video-ui \
  --date 2026-05-28 --aspect landscape
```

Open the generated `ui/index.html`, copy each scene prompt into OpenArt or Meta
AI manually, download the MP4s, rename them `scene_01.mp4` through
`scene_08.mp4`, and place them in the episode's `clips/inbox/` folder. Then:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-manual-video-assemble \
  --workspace output/kanha_ki_nanhi_leela/episodes/2026-05-28_makhan_ki_matki_shorts
```

This keeps provider use compliant: the bot prepares story, prompts, metadata
and assembly, but does not automate OpenArt's website.

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
