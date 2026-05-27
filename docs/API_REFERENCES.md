# API References

Reviewed on 2026-05-28 before scaffolding live adapters:

| Integration | Decision based on official reference | Source |
| --- | --- | --- |
| Prompt Bot | Use the OpenAI Responses API with structured output; default to configurable `gpt-5.4-mini` for the daily content task. | [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [models](https://developers.openai.com/api/docs/models) |
| Imagen | Use GA `imagen-4.0-generate-001`; it supports `1:1`, `16:9`, and `9:16` PNG image generation. | [Google Cloud Imagen 4 documentation](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/imagen/4-0-generate) |
| Imagen Python SDK | Use `google.genai` and `GenerateImagesConfig` with Vertex AI credentials. | [Generate images using text prompts](https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images) |
| LinkedIn | Use the self-serve Share on LinkedIn flow for the authenticated personal profile: `w_member_social`, asset image upload, then a UGC image post. | [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin) |
| Canva | An optional rich-video route can use Brand Template Autofill followed by MP4 export; official guidance limits production Autofill access to Canva Enterprise members. | [Autofill guide](https://www.canva.dev/docs/connect/autofill-guide/), [Exports API](https://www.canva.dev/docs/connect/api-reference/exports/) |
| YouTube | Later uploads use `videos.insert` with OAuth 2.0 and should initially set privacy to private or unlisted. | [YouTube upload guide](https://developers.google.com/youtube/v3/guides/uploading_a_video) |
| Hindi narration | Use `gpt-4o-mini-tts` with pronunciation instructions; disclose that the voice is AI-generated. | [OpenAI text-to-speech](https://developers.openai.com/api/docs/guides/text-to-speech) |
| Motion validation | Use `sora-2` for short prompt-only vertical validation clips; do not supply face-bearing input images or request copyrighted characters/music. | [OpenAI video generation with Sora](https://developers.openai.com/api/docs/guides/video-generation) |
| Children’s upload gate | Declare child-directed Krishna episodes Made for Kids and complete disclosure/rights review before upload. | [YouTube Made for Kids](https://support.google.com/youtube/answer/9528076), [altered or synthetic content](https://support.google.com/youtube/answer/14328491), [monetization policies](https://support.google.com/youtube/answer/1311392) |
| YouTube synthetic status | The upload adapter sets `status.containsSyntheticMedia=true` as a conservative disclosure even for animated AI visuals. | [YouTube video resource](https://developers.google.com/youtube/v3/docs/videos) |

Instagram Reels is a Phase 3 decision. Its account-specific access and
publication workflow should be rechecked against official documentation when
that adapter is implemented.
