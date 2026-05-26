# Project Plan

## Product Goal

Produce one daily multi-platform content package from a structured prompt, then
turn it into platform-specific assets and publish it with monitoring and explicit
controls around public posting.

## System Shape

| Stage | Bot | Input | Output | MVP status |
| --- | --- | --- | --- | --- |
| 1 | Prompt Bot | Date and editorial rules | `prompt.json` | Implemented, mock + OpenAI/Claude adapters |
| 2A | Image Bot | `image_prompt` | Supporting visual variants | Implemented, mock + Imagen adapter |
| 2A-LI | Infographic Renderer | Structured infographic copy | Exact-text LinkedIn PNG | Implemented |
| 2B | Video Bot | Script segments | Branded landscape scenes | In progress |
| 3 | Merge Bot | Scene PNGs | Landscape preview MP4 | In progress |
| 4 | Publish Bots | Assets and metadata | Platform post IDs | LinkedIn personal post completed |

## Important Design Decisions

- Start with local storage, then add Google Cloud Storage once the artifact contract
  is stable. Local output makes development and tests quick and inspectable.
- Use the owner's established LinkedIn voice: educational posts for project and
  Agile delivery professionals, paired with structured portrait infographics.
- Do not label topics as trending solely from an LLM response. A future research
  input must provide sourced trend context before the Prompt Bot makes that claim.
- Do not enable public posting by default. A failed post is recoverable; an
  incorrect automated public post is much more expensive.
- Treat vertical video exports separately: YouTube Shorts and Instagram Reels have
  different publication metadata and evolving platform constraints.

## Artifact Contract

```text
daily/YYYY-MM-DD/
  prompt.json
  images/image_square.png|svg
  images/image_landscape.png|svg
  images/image_portrait.png|svg
  images/linkedin_infographic.svg
  images/linkedin_infographic.png
  video/scenes/scene_01.png ...
  video/landscape_preview_16x9.mp4
  clips/clip_01_hook.mp4 ... clip_05_cta.mp4
  video/final_landscape_16x9.mp4
  video/short_youtube_9x16.mp4
  video/reel_instagram_9x16.mp4
  publish/*.json
  run_manifest.json
```

The LinkedIn infographic is rendered from structured text to SVG and PNG for
reliable spelling and layout. Other SVG images are mock-development placeholders;
live Imagen runs write supporting PNG files when needed.

## Delivery Phases

### Phase 1: Personal LinkedIn Image Post - Complete

Completed on May 26, 2026: member OAuth with `w_member_social`, exact-text image
generation, preview/confirmation, and one live post on the owner's profile.

Implemented control flow: `linkedin-auth` stores an authorized token only in the
local ignored `.env`; `linkedin-post` previews by default and publishes only with
an explicit `--publish` flag. Successful publication now writes a receipt and
blocks duplicate daily posts unless intentionally overridden.

### Phase 2: Video Generation And YouTube

Started with a deterministic branded-slide renderer to preserve readable text and
match the LinkedIn teaching format. It converts the generated video script into
16:9 scenes and assembles a silent local preview with FFmpeg. Next additions are
voiceover/captions, background-audio licensing rules, thumbnail selection, and
YouTube resumable upload.
Completion gate: one private/unlisted full-length YouTube upload.

### Phase 3: Vertical Distribution

Implement caption-safe 9:16 layouts, subtitles, duration enforcement, YouTube
Shorts metadata, and Instagram Reels container/publish flow.
Completion gate: approved private/test-account vertical publications.

### Phase 4: Operations

Move storage to GCS, turn on scheduler, persist run state, add idempotency,
retry/backoff, cost controls, content review option, notifications, and dashboard.
Completion gate: seven reliable daily scheduled runs before unattended posting.

## Accounts And Setup Checklist

- Google Cloud project: enable Vertex AI, configure service account, and later
  enable YouTube Data API OAuth credentials and a GCS bucket.
- OpenAI Platform account: create an API key for Prompt Bot; ChatGPT subscriptions
  are separate from API billing and credentials.
- LinkedIn member account: create a developer app, add the Share on LinkedIn
  product for `w_member_social`, then authorize posting to your own profile.
- Meta developer app: attach an Instagram professional account and obtain the
  content publishing permissions needed for Reels.
- Video provider account: validate that Canva template autofill and MP4 export
  satisfy the creative workflow before committing to it.
- Runtime: install FFmpeg on the worker image before Phase 2.

## Secrets For GitHub Actions

Do not commit keys. When each integration is enabled, add repository secrets for
`OPENAI_API_KEY`, Google Cloud authentication, LinkedIn tokens, YouTube OAuth,
Meta tokens, and video-provider credentials. Enable only the bot that has passed a
manual test.

## Your Next Actions

1. Select the Phase 2 video-generation provider and create one test clip workflow.
2. Install FFmpeg and implement landscape video assembly from generated scenes.
3. Configure YouTube OAuth and upload the first result as private or unlisted.
4. Keep LinkedIn publishing confirmation-gated during continued content calibration.
