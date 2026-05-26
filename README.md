# Content Automation Pipeline

A staged automation project for creating and distributing daily content to LinkedIn,
YouTube, YouTube Shorts, and Instagram Reels.

The starter implementation covers the first shippable slice:

- Bot 1 produces a validated `prompt.json`.
- Bot 2A produces square, landscape, and portrait image artifacts.
- The LinkedIn bot prepares a post payload and receipt without posting publicly.
- All remaining video and publishing stages are mapped in [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).

Mock mode is the default, so the pipeline is runnable before paid API access or
social account approvals exist.

## Run It Locally

```bash
cd /Users/lalitprasadsingh/VS_code/PMPSimulator/content-automation-pipeline
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

Then update `.env`:

```dotenv
PROMPT_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key
ANTHROPIC_MODEL=your_enabled_claude_model

IMAGE_PROVIDER=imagen
GCP_PROJECT_ID=your_google_cloud_project
GCP_LOCATION=us-central1
IMAGEN_MODEL=imagen-4.0-generate-001
```

Google Application Default Credentials must also be configured for Vertex AI.
LinkedIn remains deliberately non-posting until its approved organization access
and media upload flow are wired and tested.

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
