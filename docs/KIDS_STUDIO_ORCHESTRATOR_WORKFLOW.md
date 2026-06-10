# KidsStudio-Orchestrator 2D Video Workflow

Current date: 2026-06-10

This document explains the current 2D video work, the paths involved, and the step-by-step workflow for testing or continuing the work manually.

## 1. Current Goal

The current 2D video work is focused on making story videos feel more natural:

- Faces should be visible and readable.
- Mouth/lip-sync should stay anchored on the face.
- Walking should not look like a flat slide.
- Characters should sit in the scene with shadows and lighting.
- Large media files should stay on the external drive, not inside the repo.

The main demo project used for validation is:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night
```

The current output video is:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night/output/mvp_chori_night_final.mp4
```

## 2. Storage Layout

The app now resolves the 2D orchestrator root in this order:

```text
1. KIDS_STUDIO_ORCHESTRATOR_ROOT
2. /Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator
3. /Volumes/Crucial X9/Mac/2D_Video/story_studio
4. ./KidsStudio-Orchestrator inside this repo
```

The preferred external root is:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator
```

The repo-side patch root is:

```text
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.2d_patches
```

## 3. Repo Files Changed

These files live in the main project repo and should be committed to git.

```text
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/app.py
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/uv.lock
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/docs/KIDS_STUDIO_ORCHESTRATOR_WORKFLOW.md
```

Shadow patch package:

```text
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.2d_patches/src/__init__.py
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.2d_patches/src/video_pipeline/__init__.py
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.2d_patches/src/video_pipeline/asset_loader.py
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.2d_patches/src/video_pipeline/frame_renderer.py
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.2d_patches/src/video_pipeline/composer.py
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.2d_patches/src/utils/__init__.py
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.2d_patches/src/utils/janitor.py
```

## 4. External Orchestrator Files Used

These files live on the external drive. They are not tracked by this repo unless separately copied into git.

Core compiler files:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/src/video_pipeline/scene_compiler.py
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/src/video_pipeline/motion_engine.py
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/src/video_pipeline/asset_loader.py
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/src/video_pipeline/frame_renderer.py
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/src/video_pipeline/composer.py
```

Rhubarb lip-sync binary:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/bin/rhubarb
```

Background music:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/character/bg_music.mp3
```

## 5. Important Sprite Libraries

Sprite registry and library indexes:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/sprite_registry.json
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/human_library_index.json
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/animal_library_index.json
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/bird_library_index.json
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/HUMAN_LIBRARY.md
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/SPRITE_REGISTRY.md
```

Preview sheets:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/human_library_preview.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/animal_library_preview.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/bird_library_preview.png
```

Human sprite packs:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/golu_boy
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/gudiya_girl
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/ramu_man
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/sita_woman
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/dadaji_old_man
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/dadi_old_woman
```

Animal sprite packs:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/chhotu_rabbit
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/chun_chun_squirrel
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/moti_deer
```

Bird sprite packs:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/kalu_crow
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/proud_peacock
```

Current story-specific human packs:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/ramu_man/base.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/ramu_man/body.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/ramu_man/face_base.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/ramu_man/eyes.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/ramu_man/eyes_blink.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/ramu_man/metadata.json
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/ramu_man/talk
```

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/dadaji_old_man/base.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/dadaji_old_man/body.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/dadaji_old_man/face_base.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/dadaji_old_man/eyes.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/dadaji_old_man/eyes_blink.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/dadaji_old_man/metadata.json
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/sprites/dadaji_old_man/talk
```

## 6. Environment Assets

Village background and foreground overlays:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_lantern_night.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_lantern_night_foreground.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_morning_handpump.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_morning_handpump_foreground.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_road.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_road_foreground.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_well_day.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_well_day_foreground.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_evening_sunset.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_evening_sunset_foreground.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_monsoon_rainbow.png
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/assets/environments/village_monsoon_rainbow_foreground.png
```

## 7. Demo Projects

Main demo under active validation:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night/scene_manifest.json
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night/output/mvp_chori_night_final.mp4
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night/render_output
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night/vocals
```

Other story packs created during this work:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/gaon_ke_dost
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/gaon_ki_umeed
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/raga_wali_gaanv
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_demo_village
```

## 8. What Was Fixed

Step-by-step fixes completed:

1. Moved the 2D workflow to an external-drive-first root.
2. Added a repo-side shadow patch package at `.2d_patches`.
3. Added a modular asset loader that supports `base.png`, `face_base.png`, `eyes.png`, `eyes_blink.png`, accessories, wings, and Rhubarb mouth frames.
4. Added a modular frame renderer with:
   - center-anchored mouth placement
   - transparent eye overlays
   - ambient light matching
   - soft ground shadows
   - blink support
   - subtle body sway
   - procedural arms and hand motion
5. Added a composer patch that ignores macOS AppleDouble `._*.mp4` files while stitching.
6. Added a janitor patch that skips cleanup in the shadow runtime so external-drive cleanup does not block app startup.
7. Patched the external motion engine with natural walk bob and torso tilt.
8. Patched the external scene compiler to:
   - use walk transforms for grounded moving characters
   - apply foreground depth overlays
   - flatten frames before ffmpeg export
   - avoid overriding mouth anchors with stale unscaled coordinates
9. Corrected `ramu_man` and `dadaji_old_man` eye layers and anchor positions.
10. Re-tested isolated puppet rendering before running the full video compile.

## 9. Manual Render Command

Run this from the repo root:

```bash
KIDS_STUDIO_ORCHESTRATOR_ROOT="/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator" \
PYTHONPATH="/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.2d_patches:/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator" \
/Users/lalitprasadsingh/VS_code/content-automation-pipeline/.venv/bin/python -B \
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/src/video_pipeline/scene_compiler.py \
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night/scene_manifest.json
```

## 10. Manual Isolated Puppet Test

This was used to verify face/eye/mouth placement before running the full video:

```text
/private/tmp/ramu_isolated_final_tuned.png
```

Expected result:

- Eyes appear on the face, not on the torso.
- Mouth appears on the face, not beside the hairline.
- Mouth cover patch is small enough to avoid a visible side shadow.

## 11. Generated Output Files

These are generated and can be recreated:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night/render_output
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night/output/mvp_chori_night_final.mp4
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator/projects/mvp_chori_night/vocals
```

macOS AppleDouble files can appear on the external drive:

```text
._*
.DS_Store
```

The shadow patch code is designed to ignore the problematic sidecar files during mouth loading and video stitching.

## 12. Current Known Risk

The external `KidsStudio-Orchestrator` files are outside this repository. The repo commit preserves the app integration and patch layer, but the external media assets and external compiler edits must remain available at:

```text
/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator
```

If the external drive is not mounted, the app falls back to a local `KidsStudio-Orchestrator` folder, but the newest media assets and demo renders live on the external drive.
