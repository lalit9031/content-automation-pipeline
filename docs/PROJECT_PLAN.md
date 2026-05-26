# Project Plan

## Product Goal

Produce one daily multi-platform content package from a structured prompt, then
turn it into platform-specific assets and publish it with monitoring and explicit
controls around public posting.

## System Shape

| Stage | Bot | Input | Output | MVP status |
| --- | --- | --- | --- | --- |
| 1 | Prompt Bot | Date and editorial rules | `prompt.json` | Implemented, mock + OpenAI/Claude adapters |
| 2A | Image Bot | `image_prompt` | Three visual variants | Implemented, mock + Imagen adapter |
| 2B | Video Bot | Script segments | Raw video clips | Planned |
| 3 | Merge Bot | Images and clips | Landscape and vertical video | Planned |
| 4 | Publish Bots | Assets and metadata | Platform post IDs | LinkedIn payload only; all live posts gated |

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
  clips/clip_01_hook.mp4 ... clip_05_cta.mp4
  video/final_landscape_16x9.mp4
  video/short_youtube_9x16.mp4
  video/reel_instagram_9x16.mp4
  publish/*.json
  run_manifest.json
```

SVG images are mock-development placeholders; live Imagen runs write PNG files.

## Delivery Phases

### Phase 1: Personal LinkedIn Image Post

Already started in code. Next work is member OAuth with `w_member_social`, image
upload, post creation using the authenticated member as author, and failure
receipts. Completion gate: one manually confirmed post on the owner's profile.

Implemented control flow: `linkedin-auth` stores an authorized token only in the
local ignored `.env`; `linkedin-post` previews by default and publishes only with
an explicit `--publish` flag.

### Phase 2: Video Generation And YouTube

Evaluate Canva Connect autofill/export against Runway or another video provider,
then implement a provider-neutral `VideoBot`. Add FFmpeg normalization, concat,
audio licensing rules, thumbnail selection, and YouTube resumable upload.
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

1. Add repository secrets only after the relevant live provider has been tested
   locally; keep scheduled publishing disabled during calibration.
2. Create an OpenAI API key and enable the OpenAI Prompt Bot settings in `.env`.
3. Set up the Google Cloud project and confirm access to an Imagen model.
4. Create a LinkedIn developer app and enable personal-profile sharing access.
5. Decide whether the first milestone should require human approval before publish;
   that is strongly recommended while prompt quality is being calibrated.
