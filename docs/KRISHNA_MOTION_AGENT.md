# Kanha Ki Nanhi Leela Motion Agent

## Purpose

The Motion Video Agent builds short validation clips for an original, child-friendly
animated Bal Krishna series before any full episode is rendered or uploaded.
It belongs to the multi-agent workflow in
[KRISHNA_AGENT_WORKFLOW.md](KRISHNA_AGENT_WORKFLOW.md), which intentionally
separates:

1. Hindi narration voice selection.
2. Short real-motion scene generation and assembly.
3. Publication policy review and YouTube upload approval.

The characters are fictional animated story characters. Family photographs may
help the creator choose warmth or mood, but are not supplied as face references
to the motion-video API.

## Voice Selection

The separate Voice Agent generates three short Hindi narration samples:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-voice-samples
```

The samples use `gpt-4o-mini-tts` with explicit Indian Hindi pronunciation for
`यशोदा`, `गोकुल`, and `कान्हा`. OpenAI requires audiences to be told when this
voice is AI-generated.

For the pilot, the creator approved sample 1 (`marin`, warm):

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-voice-select \
  --sample sample_01_marin_warm.mp3
```

## Motion Validation

The selected provider is OpenAI Sora because it supports programmatic dynamic
clips from prompts. The validation deliberately uses text prompts rather than
the supplied photos or generated face frames: Sora currently rejects input
images containing human faces and does not generate real people.

The first live character prompt was blocked by Sora moderation on May 28, 2026.
The agent therefore defaults to an environment-motion validation that proves
trees, clouds, flower garlands, pot and light movement without depicting
people. It retains the desired character scene specification for a later
supported-provider decision, but does not bypass the rejection.

Create the two-clip environment validation plan:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-motion-plan
```

The first test clip shows an empty Gokul courtyard while the hanging butter
pot, flowers, trees and clouds move gently. The second is a warm closing shot
of the butter pot and peacock feather. The desired Kanha and Yashoda shots can
be written for review, but should not be rendered with the currently rejected
provider route:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-motion-plan --mode characters
```

For Kanha and Yashoda, initialize stable fictional character identities before
testing a provider that supports their animation:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-character-validation-init
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-image-plan --mode characters
```

The identity pack fixes recognizable design features for `KANHA_V1` and
`YASHODA_V1` and supplies a review checklist for the two desired character
motion clips. It does not claim Sora has generated those characters.

Generate real motion clips after checking the plan:

```bash
MOTION_PROVIDER=openai_sora MOTION_MODEL=sora-2 \
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-motion-generate \
  --plan output/bal_krishna_environment_motion_validation/motion_plan.json
```

Then join the approved clips:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-motion-assemble \
  --plan output/bal_krishna_environment_motion_validation/motion_plan.json
```

For validation, `sora-2` uses fast `720x1280`, 8-second vertical clips. After
the story and character design are approved, final episodes can use
`sora-2-pro` for higher-resolution output.

## Provider Boundary

Sora is not used for the Kanha and Yashoda character clips under its current
documented restrictions: real people cannot be generated, input images with
human faces are rejected, and human-likeness character uploads are blocked by
default. It remains useful for no-person environmental motion.

Vertex AI Veo is also not used for the child-character clips. In the installed
Google Gen AI SDK, the video-generation `person_generation` configuration
allows `dont_allow` or `allow_adult`; it does not provide a documented route
for generating child-person scenes. The agent stores that decision in each
motion plan.

The next evaluated candidate is Luma Dream Machine image-to-video with
fictional, creator-approved character stills only. Its API documents
image-to-video generation, and its policy prohibits sexual content involving
minors and non-consensual real-person likeness use; it does not document a
blanket prohibition on gentle fictional child-story animation. This is a
candidate route subject to private testing and provider moderation, not an
approved final-video provider yet. Runway Characters is not selected because
its published additional policy prohibits characters intended to engage users
under 18.

## Publication Gate

The separate Copyright Policy Agent prevents YouTube upload until a policy
report passes. A review must confirm:

- Story, music and sound effects are original or properly licensed.
- AI narration and AI-generated visuals are disclosed in the description.
- Characters are fictionalized or likeness permissions are documented.
- No real-face image reference was supplied to Sora.
- The content is set as `Made for Kids`.
- No copyrighted characters, copyrighted music or copied studio style are used.
- A human has watched the final file and approved the metadata.
- The stored policy source review is not stale.
- The MP4 uploaded is byte-for-byte the reviewed MP4, checked through a SHA-256 fingerprint.

For clearly animated non-realistic scenes, YouTube's policy does not require
the altered/synthetic setting. This agent deliberately sets it anyway as a
more transparent operating rule; OpenAI separately requires disclosure of its
AI-generated narration.

Generate an approval report after reviewing the final MP4:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline youtube-policy-check \
  --title "माखन चोर कान्हा और दोस्तों की मजेदार टोली" \
  --video output/bal_krishna_environment_motion_validation/video/motion_validation_preview.mp4 \
  --confirm-rights --confirm-disclosures --confirm-fictional-likenesses \
  --confirm-made-for-kids --confirm-no-face-input --human-approved
```

The command fails with a blocked report if any confirmation is omitted.

## YouTube Upload

The separate YouTube Publish Agent starts as `private` while the series is being
tested. Install the optional YouTube adapter and configure an OAuth token file
locally:

```bash
pip install -e '.[youtube]'
```

```dotenv
YOUTUBE_CLIENT_SECRETS_FILE=/absolute/path/to/client_secret.json
YOUTUBE_TOKEN_FILE=/absolute/path/to/youtube_token.json
```

Authorize the channel once:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline youtube-auth
```

Upload only after the passed policy report exists:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline youtube-upload \
  --video output/bal_krishna_environment_motion_validation/video/motion_validation_preview.mp4 \
  --title "माखन चोर कान्हा और दोस्तों की मजेदार टोली" \
  --description-file output/bal_krishna_butter_heist_episode_01/metadata/title_description.txt \
  --policy-report output/bal_krishna_environment_motion_validation/video/youtube_policy_report.json \
  --privacy private
```

The uploader always declares this story content as `Made for Kids` and sets
YouTube's synthetic-media status to `true` for transparency.

## Reviewed Policy Sources

Reviewed on May 28, 2026. The policy gate requires a refresh after 30 days.

- [OpenAI text-to-speech](https://developers.openai.com/api/docs/guides/text-to-speech)
- [OpenAI video generation with Sora](https://developers.openai.com/api/docs/guides/video-generation)
- [Luma Dream Machine API](https://docs.lumalabs.ai/docs/api)
- [Luma content policy](https://luma.ai/content-policy)
- [Runway usage policy](https://help.runwayml.com/hc/en-us/articles/17944787368595-Runway-s-Usage-Policy)
- [YouTube Made for Kids guidance](https://support.google.com/youtube/answer/9528076)
- [YouTube altered or synthetic content disclosure](https://support.google.com/youtube/answer/14328491)
- [YouTube monetization policies](https://support.google.com/youtube/answer/1311392)
