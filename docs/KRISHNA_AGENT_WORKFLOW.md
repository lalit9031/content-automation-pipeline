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
output/bal_krishna_image_validation/image_plan.json
```

## Voice Agent

For now, use the built-in AI voices with Indian-Hindi pronunciation
instructions:

```bash
PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-voice-samples
```

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

## Motion, Assembly And Upload

The real-motion validation and publication-gate commands remain documented in
[KRISHNA_MOTION_AGENT.md](KRISHNA_MOTION_AGENT.md). Current result: Sora
successfully rendered motion for the environment scenes, while a fictional
Kanha character scene was blocked by provider moderation. The agent respects
that stop and does not attempt to animate family photographs or bypass the
provider decision.

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
- [YouTube Made for Kids](https://support.google.com/youtube/answer/9528076)
- [YouTube synthetic-content disclosure](https://support.google.com/youtube/answer/14328491)
