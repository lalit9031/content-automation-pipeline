# API References

Reviewed on 2026-05-26 before scaffolding live adapters:

| Integration | Decision based on official reference | Source |
| --- | --- | --- |
| Prompt Bot | Use the OpenAI Responses API with structured output; default to configurable `gpt-5.4-mini` for the daily content task. | [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [models](https://developers.openai.com/api/docs/models) |
| Imagen | Use GA `imagen-4.0-generate-001`; it supports `1:1`, `16:9`, and `9:16` PNG image generation. | [Google Cloud Imagen 4 documentation](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/imagen/4-0-generate) |
| Imagen Python SDK | Use `google.genai` and `GenerateImagesConfig` with Vertex AI credentials. | [Generate images using text prompts](https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images) |
| LinkedIn | Implement live organization publishing only after Images API upload yields an image URN; Posts API is versioned and requires organization permission. | [LinkedIn Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api) |
| YouTube | Later uploads use `videos.insert` with OAuth 2.0 and should initially set privacy to private or unlisted. | [YouTube upload guide](https://developers.google.com/youtube/v3/guides/uploading_a_video) |

Canva/alternative video generation and Instagram Reels are Phase 2 and Phase 3
decisions. Their account-specific access and publication workflows should be
rechecked against official documentation when those adapters are implemented.
