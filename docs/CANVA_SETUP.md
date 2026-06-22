# Canva Integration Setup

Reviewed on May 26, 2026 against the Canva Connect API documentation.

## Current Access Constraint

The pipeline would use Canva Brand Template Autofill to replace scene copy in a
designed video template, then use the Export API to download an MP4. Canva's
official Autofill guide states that production access is available to Canva
Enterprise members. Members of paid plans may receive limited development trial
access, but that is not a production publishing foundation.

Until access is confirmed, the FFmpeg renderer remains the reliable video path:
it produces branded scenes, subtle motion, and SRT subtitles locally without a
Canva dependency.

## What Canva Can Add

- Professionally designed animated intro, teaching cards, and outro scenes.
- Brand fonts, colors, logo placement, and visual consistency across videos.
- Stock/video placeholders or approved background assets in the template.
- MP4 export of the completed design for later FFmpeg formatting and publishing.

## What You Can Provide

1. Your Canva plan and organization entitlement: confirm Canva Enterprise or an
   Autofill development trial shown in the developer portal.
2. A Canva Developer app Client ID. Keep any Client Secret private and place it
   only in the local `.env` used by the adapter.
3. A reusable Canva brand video template designed for text replacement.
4. The template ID and these text autofill field keys required by the adapter:
   `headline`, `hook`, `point_1`, `point_2`, `point_3`, and `cta`.
5. Brand assets: logo as PNG or SVG, color hex codes, preferred fonts, profile
   image if required, LinkedIn handle, and end-card call to action.
6. Video direction: preferred style, sample references, landscape versus
   vertical priority, voiceover preference, and licensed music choice.

Do not send API client secrets or tokens in chat, screenshots, or Git. They
belong in the ignored `.env` file on your computer.

## Implemented Adapter Flow

When Canva variables and a template ID are configured, the optional adapter:

1. Uses the configured Canva OAuth refresh token to obtain an access token.
2. Maps `prompt.json` video script fields to the template autofill fields.
3. Creates an Autofill design job and polls until the design is ready.
4. Starts an MP4 export job, polls its status, and downloads the result.
5. Writes the MP4 to `video/canva_export.mp4` in the daily output directory.

Canva refresh tokens are single-use. On each token refresh, the adapter saves
the replacement `CANVA_REFRESH_TOKEN` back to the ignored local `.env` file so
the next pipeline run can authenticate without repeating OAuth authorization.

## Official References

- [Canva Brand Template Autofill guide](https://www.canva.dev/docs/connect/autofill-guide/)
- [Canva Autofills API](https://www.canva.dev/docs/connect/api-reference/autofills/)
- [Canva Exports API](https://www.canva.dev/docs/connect/api-reference/exports/)
- [Canva authentication](https://www.canva.dev/docs/connect/authentication/)
