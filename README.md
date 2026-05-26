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
