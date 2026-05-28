# Kanha Ki Nanhi Leela Agent Workflow

## One Agent Per Job

This children's-animation workflow assigns one responsibility to each agent.
Agents communicate through reviewed files under `output/`; a later agent does
not silently change an earlier agent's approved work.

| Order | Agent | Responsibility | Main Output |
| --- | --- | --- | --- |
| 1 | Story Agent | Hindi story, moral, scene brief and metadata | Script and storyboard |
| 2 | Voice Agent | Hindi pronunciation samples and selected narration | MP3 narration |
| 3 | Image Agent | Original settings, storyboards and thumbnail assets | Image plan and still assets |
| 4 | Motion Video Agent | Short real-motion animated scene clips | Scene MP4 files |
| 5 | Assembly Agent | Combine clips, narration, captions and licensed sound | Final review MP4 |
| 6 | Copyright Policy Agent | Rights, safety, disclosure and platform checks | Approval report and video fingerprint |
| 7 | YouTube Publish Agent | Upload an approved file only | Private/unlisted video ID |

Create the workspace contracts:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-agents-init
```

This writes:

```text
output/kanha_ki_nanhi_leela/agent_manifest.json
output/kanha_ki_nanhi_leela/voice_source_policy.json
output/kanha_ki_nanhi_leela/character_motion_validation_protocol.json
output/bal_krishna_image_validation/image_plan.json
output/bal_krishna_character_identity_validation/image_plan.json
```

## Voice Agent

For now, use the built-in AI voices with Indian-Hindi pronunciation
instructions:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-voice-samples
```

Selected production narrator for the pilot:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-voice-select \
  --sample sample_01_marin_warm.mp3
```

This records the built-in `marin` voice as creator-approved; the final video
description must still disclose that its narration is AI-generated.

When custom samples are considered later:

- The creator's own voice can be considered with recorded consent.
- A narrator's recording can be considered only with explicit written
  permission and provider-required voice-model consent.
- Publicly available, royalty-free, Creative Commons or open-source recordings
  are not enough by themselves to clone the speaker's voice.
- Do not use actor, singer, public figure, movie, television, podcast or
  YouTube audio as a voice-cloning source.

OpenAI custom voices are available only to eligible customers and require a
consent recording plus a matching sample recording. Until that is confirmed,
the built-in TTS voices remain the approved production route.

## Image Agent

The Image Agent maintains independent original image prompts. During provider
validation it uses environment assets without real faces:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-image-plan
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-image-generate \
  --plan output/bal_krishna_image_validation/image_plan.json
```

With the default `IMAGE_PROVIDER=mock`, this verifies the workflow using local
SVG placeholders. Live assets can later use configured Imagen; any character
artwork must remain fictional and pass human review.

## Character Identity And Motion Review

Character motion cannot be validated by simply describing "Krishna" in every
prompt: Kanha and Yashoda need locked, reviewable identities. Initialize the
character pack:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-character-validation-init
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-image-plan --mode characters
```

The pack defines `KANHA_V1` and `YASHODA_V1` with stable hair, costume,
accessories and color cues. After the generated identity stills are approved,
the Motion Video Agent tests only two five-second private actions:

- Kanha sees the hanging butter pot, blinks and smiles.
- Yashoda gently hugs Kanha.

The reviewer checks identity consistency, natural movement, hand/eye/clothing
quality, child safety and absence of copyrighted assets or real-person
resemblance before a longer episode is attempted.

After approving concept previews, write an approval receipt that binds the
approved designs to the exact files:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-character-approve \
  --kanha-image output/bal_krishna_character_identity_validation/images/kanha_v1_concept_preview.png \
  --yashoda-image output/bal_krishna_character_identity_validation/images/yashoda_v1_concept_preview.png
```

This approves the fictional designs for private motion evaluation only. It
does not approve public distribution or grant permission to use a real
person's likeness.

## No-Subscription Pilot Motion

Luma is optional, not required for the pilot. The economical route renders a
local 2.5D animated shot from the approved fictional image with FFmpeg:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-local-kanha-motion-plan
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-motion-generate \
  --plan output/bal_krishna_local_kanha_motion_validation/motion_plan.json
```

This produces a smooth five-second vertical camera-motion test using only the
approved `KANHA_V1` PNG. It uses no paid generation API and no family
photograph. It proves style, timing and video assembly; it does not claim
Kanha blinks or changes expression. Later local shots can add separate
foreground layers for swinging pots, drifting clouds, moving leaves, sparkles
and captions.

## Manual OpenArt / Meta AI Daily Studio

For one publishable video per day, the cleanest low-cost workflow is now a
manual generation studio. The bot prepares everything except provider-side
clip generation:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-daily-video-ui \
  --date 2026-05-28
```

For a landscape YouTube version instead of a Short:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-daily-video-ui \
  --date 2026-05-28 --aspect landscape
```

This creates an episode workspace:

```text
output/kanha_ki_nanhi_leela/episodes/2026-05-28_makhan_ki_matki_shorts/
```

Important files:

- `ui/index.html` - local dashboard with clean story, scene prompts, copy buttons and policy notes.
- `story_script.md` - Hindi narration and on-screen text.
- `scene_prompts.json` - OpenArt and Meta AI prompt per scene.
- `youtube_metadata.md` - title, description, disclosure and hashtags.
- `clips/inbox/` - drop downloaded MP4 clips here.
- `clip_drop_guide.md` - exact clip names expected by the assembler.

Generate each scene manually in OpenArt or Meta AI, download each MP4 and rename
the clips exactly:

```text
scene_01.mp4
scene_02.mp4
...
scene_08.mp4
```

Place them in `clips/inbox/`, then assemble the review video:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-manual-video-assemble \
  --workspace output/kanha_ki_nanhi_leela/episodes/2026-05-28_makhan_ki_matki
```

The assembler normalizes all clips to the episode format, combines them, and
writes the review render:

- Shorts: `720x1280`
- Landscape: `1280x720`

```text
video/assembled_review.mp4
video/subtitles_hi.srt
```

The policy agent and YouTube upload gate still run after human review. The bot
does not automate OpenArt's website because OpenArt's terms prohibit automated
access outside its official website/app. Meta AI may be tested, but its
commercial-use status for the exact video feature should be reviewed before
public monetized upload.

## Motion, Assembly And Upload

The real-motion validation and publication-gate commands remain documented in
[KRISHNA_MOTION_AGENT.md](KRISHNA_MOTION_AGENT.md). Current result: Sora
successfully rendered motion for the environment scenes, while a fictional
Kanha character scene was blocked by provider moderation. The agent respects
that stop and does not attempt to animate family photographs or bypass the
provider decision. Under Sora's current documented restrictions, it is not the
character-animation provider for Kanha or Yashoda; a future character provider
must explicitly allow fictional human-like character consistency tests.

An optional higher-motion candidate is Luma Dream Machine image-to-video using only
approved fictional identity stills. This is an inference from its documented
API capabilities and content policy, not a promise that each generation will
pass moderation. Runway Characters is not selected because its published
additional policy disallows characters intended to engage users under 18.

To begin that private evaluation, configure a Luma API key locally:

```dotenv
LUMAAI_API_KEY=
LUMA_IMAGE_MODEL=photon-1
LUMA_VIDEO_MODEL=ray-2
```

Generate original fictional identity stills for review:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-luma-identity-generate
```

After you approve the generated `KANHA_V1` still, use the `source_url` stored
in `identity_generation_receipt.json` to create one five-second motion plan:

```bash
MOTION_PROVIDER=luma_dream_machine \
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-luma-kanha-motion-plan \
  --approved-image-url "https://approved-fictional-kanha-image-url" \
  --confirm-identity-approved
```

Then generate only that private motion test:

```bash
MOTION_PROVIDER=luma_dream_machine \
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-motion-generate \
  --plan output/bal_krishna_luma_kanha_motion_validation/motion_plan.json
```

## Shared Safety Rules

- No family photo is sent as a face reference to a motion provider.
- No imitation of named animation studios or copyrighted cartoon properties.
- No copyrighted music without a platform-appropriate license.
- AI-generated narration is disclosed.
- Child-directed stories are configured as `Made for Kids`.
- Upload requires human approval and a policy report matching the exact MP4
  fingerprint.

## Sources

Reviewed May 28, 2026:

- [OpenAI Text-to-Speech and custom voice consent](https://developers.openai.com/api/docs/guides/text-to-speech)
- [OpenAI video generation with Sora](https://developers.openai.com/api/docs/guides/video-generation)
- [Luma Dream Machine API](https://docs.lumalabs.ai/docs/api)
- [Luma content policy](https://luma.ai/content-policy)
- [Runway usage policy](https://help.runwayml.com/hc/en-us/articles/17944787368595-Runway-s-Usage-Policy)
- [YouTube Made for Kids](https://support.google.com/youtube/answer/9528076)
- [YouTube synthetic-content disclosure](https://support.google.com/youtube/answer/14328491)
