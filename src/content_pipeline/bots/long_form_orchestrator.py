"""
long_form_orchestrator.py
=========================
The master coordinator for long-form video generation.

Connects every component of the pipeline in order:
    1. SmartPromptExpander  → expand raw prompt into 7-dimension context
    2. ScriptEngine         → break into N scenes with narrative arc
    3. ComfyUI (Image)      → generate source image for Scene 1
    4. QA Audit (Image)     → verify image quality before video generation
    5. ComfyUI (Video)      → generate each 5-6s clip
    6. QA Audit (Video)     → verify each clip
    7. LastFrameExtractor   → extract last frame for next clip's start image
    8. VideoAssembler       → stitch all clips into final MP4
    9. Final summary report → timing, quality, file info

Audio is PARKED — the pipeline slot is reserved but skipped for now.
Will be activated when audio pipeline is stable.

Usage:
    from content_pipeline.bots.long_form_orchestrator import LongFormOrchestrator
    from content_pipeline.config import Settings

    orch = LongFormOrchestrator(Settings.from_environment())
    result = orch.run(
        raw_prompt="girl walking in rain forest toward a river",
        target_seconds=30,
        output_dir=Path("output/videos/"),
    )
    print(result["summary"])
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from content_pipeline.config import Settings
from content_pipeline.bots.prompt_expander import SmartPromptExpander, PromptContext
from content_pipeline.bots.script_engine import ScriptEngine, SceneDescription
from content_pipeline.bots.last_frame_extractor import LastFrameExtractor
from content_pipeline.bots.video_assembler import VideoAssembler
from content_pipeline.bots.video_agent_orchestrator import VideoAgentOrchestrator
from content_pipeline.bots.motion import MotionClip, MotionPlan, ComfyUIMotionProvider
from content_pipeline.bots.comfy_client import ComfyUIClient, load_workflow_json, customize_txt2img_workflow
from content_pipeline.bots.qa_auditor import QAVisualAuditor


# ---------------------------------------------------------------------------
# ClipResult — result of a single clip generation attempt
# ---------------------------------------------------------------------------

@dataclass
class ClipResult:
    """Outcome of generating a single video clip."""
    scene_number: int
    clip_path: Optional[Path] = None
    last_frame_path: Optional[Path] = None
    status: str = "PENDING"          # PENDING | SUCCESS | FAIL | SKIPPED
    attempts: int = 0
    generation_time_seconds: float = 0.0
    qa_result: dict = field(default_factory=dict)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# LongFormOrchestrator
# ---------------------------------------------------------------------------

class LongFormOrchestrator:
    """
    Master coordinator for long-form video generation.

    Produces:
    - Single clip (5-6s) for test runs
    - Multi-clip assembled video (30s, 1min, 5min+) for YouTube

    Architecture:
        raw_prompt
            │
            ▼
        SmartPromptExpander  (7-dimension context)
            │
            ▼
        ScriptEngine  (N scene descriptions with narrative arc)
            │
            ▼
        ┌── For each scene ──────────────────────────────────────┐
        │   Image source: generated image OR last frame of prev  │
        │       │                                                 │
        │       ▼                                                 │
        │   QA Audit (image) → retry up to 3x if FAIL           │
        │       │                                                 │
        │       ▼                                                 │
        │   Video Generation (ComfyUI LTXV)                      │
        │       │                                                 │
        │       ▼                                                 │
        │   QA Audit (video) → retry up to 3x if FAIL           │
        │       │                                                 │
        │       ▼                                                 │
        │   LastFrameExtractor → save last frame for next scene  │
        └────────────────────────────────────────────────────────┘
            │
            ▼
        VideoAssembler  (stitch all clips → final MP4)
            │
            ▼
        Summary Report
    """

    MAX_CLIP_ATTEMPTS = 3
    MAX_IMAGE_ATTEMPTS = 3

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.expander = SmartPromptExpander()
        self.script_engine = ScriptEngine()
        self.frame_extractor = LastFrameExtractor()
        self.assembler = VideoAssembler()
        self.qa_auditor = QAVisualAuditor(settings)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------


    def run_poem(
        self,
        poem_scenes: list[dict],
        output_dir=None,
        job_name: str = "poem_video",
    ) -> dict:
        """
        Run the poem video pipeline.

        Unlike run(), this method:
          1. Accepts explicit per-scene image + video prompts (no ScriptEngine).
          2. Generates a fresh Flux keyframe image for EVERY scene.
          3. Each scene: Flux image -> ComfyUI restart -> LTXV animate.
          4. This gives each verse of the poem a proper illustration.

        Args:
            poem_scenes: List of dicts, each with:
                - image_prompt: Flux prompt for the scene keyframe image
                - video_prompt: LTXV prompt for animating the keyframe
                - title: Human-readable scene name
            output_dir: Where to save outputs
            job_name: Output folder name

        Returns:
            dict with status, final_video_path, etc.
        """
        import os
        import time as _time

        job_start = _time.time()
        out_dir = output_dir or Path("output/videos")
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        job_dir = out_dir / job_name
        job_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = job_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = job_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        images_dir = job_dir / "keyframes"
        images_dir.mkdir(parents=True, exist_ok=True)

        print("\n" + "=" * 70)
        print("POEM VIDEO PIPELINE  (per-scene Flux keyframes)")
        print("=" * 70)
        print(f"Scenes   : {len(poem_scenes)}")
        print(f"Output   : {job_dir}")
        print("=" * 70)

        from content_pipeline.bots.comfy_client import ComfyUIClient
        client = ComfyUIClient(settings=self.settings)

        clip_paths = []
        clip_results_info = []

        for scene_dict in poem_scenes:
            scene_idx = scene_dict["scene"]
            title = scene_dict.get("title", f"Scene {scene_idx}")
            image_prompt = scene_dict["image_prompt"]
            video_prompt = scene_dict["video_prompt"]

            print(f"\n--- Scene {scene_idx}/{len(poem_scenes)}: {title} ---")

            # ----------------------------------------------------------------
            # Phase A: Flux image generation
            # ----------------------------------------------------------------
            print(f"  [Flux] Generating keyframe image for scene {scene_idx}...")
            keyframe_path = images_dir / f"scene_{scene_idx:02d}_keyframe.png"
            server_proc, server_log = None, None
            started_server = False

            try:
                if not client._is_listening():
                    print("  [Auto-Memory] Starting ComfyUI (Flux phase)...")
                    server_proc, server_log = client._start_server()
                    started_server = True
                    if not client._wait_listening():
                        print(f"  ERROR: ComfyUI failed to start for scene {scene_idx} Flux phase")
                        clip_results_info.append({"scene": scene_idx, "status": "FAIL", "error": "ComfyUI start failed"})
                        continue

                img_bytes = self._generate_image(image_prompt)
                keyframe_path.write_bytes(img_bytes)
                print(f"  [Flux] Keyframe saved: {keyframe_path.name} ({len(img_bytes)//1024}KB)")

            except Exception as e:
                print(f"  [Flux] Image generation failed: {e}")
                clip_results_info.append({"scene": scene_idx, "status": "FAIL", "error": str(e)})
                continue

            finally:
                # Always restart ComfyUI after Flux to flush Flux weights before LTXV
                if server_proc:
                    print("  [RAM] Restarting ComfyUI — flushing Flux before LTXV...")
                    server_proc.terminate()
                    try:
                        server_proc.wait(timeout=20)
                    except Exception:
                        server_proc.kill()
                        server_proc.wait()
                    if server_log:
                        server_log.close()
                    _time.sleep(4)
                    print("  [RAM] Flux cleared. Starting LTXV phase...")
                    server_proc, server_log = client._start_server()
                    started_server = True
                    if not client._wait_listening():
                        print(f"  ERROR: ComfyUI failed to restart for scene {scene_idx} LTXV phase")
                        clip_results_info.append({"scene": scene_idx, "status": "FAIL", "error": "LTXV start failed"})
                        continue

            # ----------------------------------------------------------------
            # Phase B: LTXV video generation from keyframe
            # ----------------------------------------------------------------
            print(f"  [LTXV] Animating keyframe -> video clip...")
            clip_path = clips_dir / f"clip_{scene_idx:02d}.mp4"
            scene_start = _time.time()

            try:
                # Build a minimal SceneDescription for _generate_clip
                from content_pipeline.bots.script_engine import SceneDescription
                scene_obj = SceneDescription(
                    scene_number=scene_idx,
                    total_scenes=len(poem_scenes),
                    raw_prompt=video_prompt,
                    duration_seconds=4,
                    action_modifier="",
                    camera_modifier="medium shot, face visible and sharp",
                    environment_detail="",
                    narrative_note=title,
                    is_first=(scene_idx == 1),
                    is_last=(scene_idx == len(poem_scenes)),
                )
                clip_result = self._generate_clip(
                    scene=scene_obj,
                    start_image_path=keyframe_path,
                    base_video_prompt=video_prompt,
                    clips_dir=clips_dir,
                    frames_dir=frames_dir,
                    raw_prompt=video_prompt,
                )
                scene_time = _time.time() - scene_start

                if clip_result.status == "SUCCESS" and clip_result.clip_path:
                    clip_paths.append(clip_result.clip_path)
                    size_mb = round(clip_result.clip_path.stat().st_size / (1024*1024), 1)
                    print(f"  [OK] Scene {scene_idx} done in {scene_time:.0f}s — {size_mb}MB")
                    clip_results_info.append({"scene": scene_idx, "status": "SUCCESS", "time": scene_time, "size_mb": size_mb})
                else:
                    print(f"  [FAIL] Scene {scene_idx}: {clip_result.error}")
                    clip_results_info.append({"scene": scene_idx, "status": "FAIL", "error": clip_result.error})

            except Exception as e:
                print(f"  [LTXV] Video generation failed: {e}")
                clip_results_info.append({"scene": scene_idx, "status": "FAIL", "error": str(e)})

            finally:
                # Stop ComfyUI after each scene to free RAM completely
                if server_proc:
                    print(f"  [RAM] Stopping ComfyUI after scene {scene_idx} to free RAM...")
                    server_proc.terminate()
                    try:
                        server_proc.wait(timeout=15)
                    except Exception:
                        server_proc.kill()
                        server_proc.wait()
                    if server_log:
                        server_log.close()
                    _time.sleep(3)

        # ----------------------------------------------------------------
        # Assemble all clips
        # ----------------------------------------------------------------
        print(f"\n[Assembly] Joining {len(clip_paths)}/{len(poem_scenes)} clips...")
        if not clip_paths:
            return {"status": "FAIL", "error": "No clips generated", "final_video_path": None}

        final_path = job_dir / f"{job_name}_final.mp4"
        try:
            self.assembler.assemble(
                clip_paths=clip_paths,
                output_path=final_path,
                crossfade_seconds=0.5 if len(clip_paths) > 1 else 0.0,
                crf=18,
            )
        except Exception as e:
            return {"status": "FAIL", "error": f"Assembly failed: {e}", "final_video_path": None}

        total_time = _time.time() - job_start

        print("\n" + "=" * 70)
        print("POEM VIDEO SUMMARY")
        print("=" * 70)
        for info in clip_results_info:
            status = info["status"]
            sc = info["scene"]
            if status == "SUCCESS":
                print(f"  Scene {sc:02d}: SUCCESS  {info.get('time',0):.0f}s  {info.get('size_mb','?')}MB")
            else:
                print(f"  Scene {sc:02d}: FAIL     {info.get('error','')}")
        print(f"Total time  : {total_time/60:.1f} minutes")
        print(f"Final video : {final_path}")
        size_mb = round(final_path.stat().st_size / (1024*1024), 1) if final_path.exists() else "?"
        print(f"Size        : {size_mb} MB")
        print("=" * 70)

        return {
            "status": "SUCCESS",
            "final_video_path": str(final_path),
            "total_time_seconds": round(total_time, 1),
            "scenes": clip_results_info,
        }

    def run(
        self,
        raw_prompt: str,
        target_seconds: int = 6,
        output_dir: Optional[Path] = None,
        job_name: Optional[str] = None,
        detail_level: str = "full",
    ) -> dict[str, Any]:
        """
        Run the full long-form video generation pipeline.

        Args:
            raw_prompt:      User's raw prompt (e.g. "girl walking in rain forest")
            target_seconds:  Total video duration desired (6 = single clip test, 30 = long-form test)
            output_dir:      Where to save all outputs. Defaults to output/videos/
            job_name:        Optional name prefix for output files.
            detail_level:    Prompt detail level: "minimal" | "standard" | "full"

        Returns:
            dict with keys: status, final_video_path, clips, summary, total_time_seconds
        """
        job_start = time.time()

        # Setup directories
        out_dir = output_dir or Path("output/videos")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = (job_name or raw_prompt[:30]).replace(" ", "_").replace("/", "_")
        job_dir = out_dir / safe_name
        job_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = job_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        clips_dir = job_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'=' * 70}")
        print(f"LONG-FORM VIDEO PIPELINE")
        print(f"{'=' * 70}")
        print(f"Prompt  : {raw_prompt}")
        print(f"Target  : {target_seconds}s")
        print(f"Output  : {job_dir}")
        print(f"{'=' * 70}\n")

        # Temporarily disable auto-release memory during the pipeline run so that
        # the ComfyUI server stays running and warm between images/videos.
        import os
        orig_auto_release = os.environ.get("COMFYUI_AUTO_RELEASE_MEMORY")
        os.environ["COMFYUI_AUTO_RELEASE_MEMORY"] = "false"

        server_proc = None
        server_log = None
        started_server = False

        try:
            client = ComfyUIClient(
                base_url=self.settings.comfyui_url,
                timeout_seconds=self.settings.comfyui_timeout_seconds,
                settings=self.settings,
            )
            if not client._is_listening():
                print("[Auto-Memory] Starting ComfyUI server for long-form pipeline...")
                server_proc, server_log = client._start_server()
                started_server = True
                if not client._wait_listening():
                    if server_log:
                        server_log.close()
                    print("Failed to start ComfyUI server. Attempting to clean up...")
                    if server_proc:
                        server_proc.terminate()
                    return self._fail_result("Failed to start ComfyUI server", time.time() - job_start)

            # ---------------------------------------------------------------
            # Step 1: Expand prompt into 7-dimension context
            # ---------------------------------------------------------------
            print("[Step 1] Expanding prompt with SmartPromptExpander...")
            ctx = self.expander.extract_context(raw_prompt, detail_level=detail_level)
            image_prompt = self.expander.build_image_prompt(ctx)
            video_prompt_base = self.expander.build_video_prompt(ctx)
            print(f"  Subject : {ctx.subject_age_desc}")
            print(f"  Scene   : {ctx.scene_category} / {ctx.scene_type}")
            print(f"  Motion  : {ctx.motion_description[:60]}...")
            print(f"  Image prompt: {len(image_prompt)} chars")
            print(f"  Video prompt: {len(video_prompt_base)} chars")

            # ---------------------------------------------------------------
            # Step 2: Build scene list with ScriptEngine
            # ---------------------------------------------------------------
            print(f"\n[Step 2] Building scene storyboard ({target_seconds}s)...")
            scenes = self.script_engine.build_scene_list(raw_prompt, target_seconds=target_seconds)
            try:
                print(self.script_engine.describe_plan(scenes))
            except UnicodeEncodeError:
                safe = self.script_engine.describe_plan(scenes).encode('ascii', errors='replace').decode('ascii')
                print(safe)

            # ---------------------------------------------------------------
            # Step 3: Generate source image (Scene 1 start image)
            # ---------------------------------------------------------------
            print(f"\n[Step 3] Generating source image for Scene 1...")
            start_image_path = job_dir / "scene_01_source_image.png"
            image_ok = False

            for img_attempt in range(1, self.MAX_IMAGE_ATTEMPTS + 1):
                print(f"  Image generation attempt {img_attempt}/{self.MAX_IMAGE_ATTEMPTS}...")
                try:
                    img_bytes = self._generate_image(image_prompt)
                    start_image_path.write_bytes(img_bytes)

                    # QA audit the image before using it
                    print(f"  Running QA audit on generated image...")
                    img_qa = self.qa_auditor.audit_image(img_bytes, raw_prompt)
                    print(f"  Image QA: {img_qa['status']}" + (f" — {img_qa.get('reason', '')}" if img_qa['status'] == 'FAIL' else ""))

                    if img_qa["status"] == "PASS":
                        image_ok = True
                        break
                    else:
                        print(f"  Image QA failed: {img_qa.get('reason')}. Regenerating...")

                except Exception as e:
                    print(f"  Image generation error (attempt {img_attempt}): {e}")
                    if img_attempt == self.MAX_IMAGE_ATTEMPTS:
                        return self._fail_result(
                            f"Image generation failed after {self.MAX_IMAGE_ATTEMPTS} attempts: {e}",
                            time.time() - job_start
                        )

            if not image_ok:
                print(f"  Warning: Image QA did not pass after {self.MAX_IMAGE_ATTEMPTS} attempts. Using last result.")

            print(f"  Source image saved: {start_image_path}")

            # ---------------------------------------------------------------
            # MEMORY CHECKPOINT: Restart ComfyUI between image and video
            # ---------------------------------------------------------------
            # Flux image model uses ~11GB VRAM + ~4GB RAM offload.
            # LTXV video model uses ~12.4GB VRAM + ~6GB RAM offload.
            # Running both in the same ComfyUI session means they compete for
            # the same 24GB VRAM pool — causing RAM overflow as the offload
            # buffer fills up.
            # Solution: restart ComfyUI between phases to flush Flux completely.
            if started_server and server_proc:
                print("\n[RAM Checkpoint] Restarting ComfyUI to flush Flux model from VRAM before video generation...")
                server_proc.terminate()
                try:
                    server_proc.wait(timeout=20)
                except Exception:
                    server_proc.kill()
                    server_proc.wait()
                if server_log:
                    server_log.close()
                print("[RAM Checkpoint] Flux model cleared from VRAM. Starting fresh for LTXV video generation...")
                import time as _time
                _time.sleep(3)  # Brief pause to let OS reclaim memory
                server_proc, server_log = client._start_server()
                if not client._wait_listening():
                    return self._fail_result("Failed to restart ComfyUI for video phase", time.time() - job_start)
                print("[RAM Checkpoint] ComfyUI restarted clean. LTXV will now have full VRAM budget.\n")

            # ---------------------------------------------------------------
            # Step 4: Generate each video clip
            # ---------------------------------------------------------------
            print(f"\n[Step 4] Generating {len(scenes)} video clip(s)...")
            clip_results: list[ClipResult] = []
            current_start_image = start_image_path

            for scene in scenes:
                clip_result = self._generate_clip(
                    scene=scene,
                    start_image_path=current_start_image,
                    base_video_prompt=video_prompt_base,
                    clips_dir=clips_dir,
                    frames_dir=frames_dir,
                    raw_prompt=raw_prompt,
                )
                clip_results.append(clip_result)

                if clip_result.status == "SUCCESS" and clip_result.last_frame_path:
                    # Use this clip's last frame as the next clip's start image
                    current_start_image = clip_result.last_frame_path
                    print(f"  Scene {scene.scene_number}: SUCCESS → last frame extracted for Scene {scene.scene_number + 1}")
                else:
                    print(f"  Scene {scene.scene_number}: {clip_result.status} — {clip_result.error or 'No error info'}")
                    if scene.is_last or clip_result.clip_path is None:
                        break  # Can't continue without a clip

            # ---------------------------------------------------------------
            # Step 5: Assemble all clips into final video
            # ---------------------------------------------------------------
            successful_clips = [r.clip_path for r in clip_results if r.clip_path and r.clip_path.exists()]
            print(f"\n[Step 5] Assembling {len(successful_clips)}/{len(scenes)} clips into final video...")

            final_video_path = job_dir / f"{safe_name}_final.mp4"

            if not successful_clips:
                return self._fail_result("No clips were successfully generated.", time.time() - job_start)

            try:
                self.assembler.assemble(
                    clip_paths=successful_clips,
                    output_path=final_video_path,
                    crossfade_seconds=0.5 if len(successful_clips) > 1 else 0.0,
                )
            except Exception as e:
                logging.error(f"[LongFormOrchestrator] Assembly failed: {e}")
                return self._fail_result(f"Video assembly failed: {e}", time.time() - job_start)

            total_time = time.time() - job_start
            total_duration = sum(r.generation_time_seconds for r in clip_results)

            # ---------------------------------------------------------------
            # Step 6: Build summary
            # ---------------------------------------------------------------
            summary = self._build_summary(
                raw_prompt=raw_prompt,
                clip_results=clip_results,
                final_video_path=final_video_path,
                source_image_path=start_image_path,
                total_time=total_time,
            )
            print(f"\n{summary}")

            return {
                "status": "SUCCESS",
                "final_video_path": str(final_video_path),
                "source_image_path": str(start_image_path),
                "clips": [
                    {
                        "scene": r.scene_number,
                        "path": str(r.clip_path) if r.clip_path else None,
                        "status": r.status,
                        "attempts": r.attempts,
                        "time_seconds": round(r.generation_time_seconds, 1),
                        "qa": r.qa_result,
                    }
                    for r in clip_results
                ],
                "total_time_seconds": round(total_time, 1),
                "summary": summary,
            }
        finally:
            # Clean up ComfyUI server if we started it
            if started_server and server_proc:
                print("[Auto-Memory] Terminating long-form ComfyUI server to release RAM/VRAM...")
                server_proc.terminate()
                try:
                    server_proc.wait(timeout=15)
                except Exception:
                    server_proc.kill()
                    server_proc.wait()
                if server_log:
                    server_log.close()
                print("[Auto-Memory] ComfyUI server terminated successfully.")

            if orig_auto_release is not None:
                os.environ["COMFYUI_AUTO_RELEASE_MEMORY"] = orig_auto_release
            else:
                os.environ.pop("COMFYUI_AUTO_RELEASE_MEMORY", None)

    # ------------------------------------------------------------------
    # Internal: Single clip generation with QA retry loop
    # ------------------------------------------------------------------

    def _generate_clip(
        self,
        scene: SceneDescription,
        start_image_path: Path,
        base_video_prompt: str,
        clips_dir: Path,
        frames_dir: Path,
        raw_prompt: str,
    ) -> ClipResult:
        """Generate a single video clip with QA retry loop."""
        clip_path = clips_dir / f"clip_{scene.scene_number:02d}.mp4"
        result = ClipResult(scene_number=scene.scene_number)
        clip_start = time.time()

        # Build scene-specific video prompt
        scene_video_prompt = (
            f"{base_video_prompt} "
            f"Action this scene: {scene.action_modifier}. "
            f"Camera this scene: {scene.camera_modifier}. "
            f"Environment: {scene.environment_detail}."
        )

        print(f"\n  ── Scene {scene.scene_number}/{scene.total_scenes} ──────────────────────")
        print(f"  Action : {scene.action_modifier[:60]}")
        print(f"  Camera : {scene.camera_modifier[:60]}")
        print(f"  Source : {start_image_path.name}")

        for attempt in range(1, self.MAX_CLIP_ATTEMPTS + 1):
            result.attempts = attempt
            print(f"  Clip generation attempt {attempt}/{self.MAX_CLIP_ATTEMPTS}...")

            try:
                # Build MotionClip and MotionPlan for the existing provider
                motion_clip = MotionClip(
                    id=f"scene_{scene.scene_number:02d}",
                    title=f"Scene {scene.scene_number}",
                    duration_seconds=scene.duration_seconds,
                    prompt=scene_video_prompt,
                    output_file=str(clip_path),
                    reference_image_file=str(start_image_path),
                )
                motion_plan = MotionPlan(
                    project_id=f"longform_{scene.scene_number}",
                    title="Long-form video",
                    provider="comfyui_local",
                    model="ltxv-13b-0.9.8-dev-fp8.safetensors",
                    size="768x512",  # Full quality resolution — safe on 64GB RAM system
                    clips=[motion_clip],
                    provider_rules=[],
                )

                # Use existing VideoAgentOrchestrator (has its own QA retry loop)
                video_orchestrator = VideoAgentOrchestrator(self.settings)
                loop_result = video_orchestrator.run_video_generation_loop(
                    clip=motion_clip,
                    plan=motion_plan,
                    destination=clip_path,
                    max_attempts=2,  # Inner loop: 2 attempts; outer loop adds more
                )

                if loop_result["status"] == "SUCCESS" and clip_path.exists():
                    # Extract last frame for chaining
                    last_frame = self.frame_extractor.extract(
                        clip_path,
                        output_dir=frames_dir,
                    )
                    result.clip_path = clip_path
                    result.last_frame_path = last_frame
                    result.status = "SUCCESS"
                    result.qa_result = loop_result
                    result.generation_time_seconds = time.time() - clip_start
                    print(f"  ✓ Clip {scene.scene_number} generated in {result.generation_time_seconds:.0f}s")
                    return result
                else:
                    print(f"  Attempt {attempt} did not pass QA. Retrying...")

            except Exception as e:
                logging.warning(f"[LongFormOrchestrator] Clip {scene.scene_number} attempt {attempt} error: {e}")
                print(f"  Error on attempt {attempt}: {e}")

        # All attempts exhausted
        result.status = "FAIL"
        result.error = f"Failed after {self.MAX_CLIP_ATTEMPTS} attempts"
        result.generation_time_seconds = time.time() - clip_start

        # Return whatever partial clip exists (best effort)
        if clip_path.exists():
            result.clip_path = clip_path
            try:
                result.last_frame_path = self.frame_extractor.extract(clip_path, output_dir=frames_dir)
            except Exception:
                pass

        return result

    # ------------------------------------------------------------------
    # Internal: Image generation
    # ------------------------------------------------------------------

    def _generate_image(self, image_prompt: str) -> bytes:
        """
        Generate a source image using Flux at 768x512 (safe VRAM, no black screen),
        then resize to 1280x720 using high-quality lanczos + unsharp sharpening.

        SAFE settings:
          - 768x512 = Flux native resolution, low VRAM (no driver crash / black screen)
          - 1024x1024 caused GPU driver reset (black screen) due to VRAM overflow
          - ComfyUI restarted fresh each call to prevent KSampler caching issue
            (caching causes scenes 2-6 to duplicate scene 1 when server stays running)
        """
        import os
        import io

        # Force auto-manage mode: ComfyUI starts fresh for EACH image call
        # This is the only reliable way to prevent ComfyUI KSampler caching
        orig = os.environ.get("COMFYUI_AUTO_RELEASE_MEMORY")
        os.environ["COMFYUI_AUTO_RELEASE_MEMORY"] = "true"

        try:
            client = ComfyUIClient(
                base_url=self.settings.comfyui_url,
                timeout_seconds=self.settings.comfyui_timeout_seconds,
                settings=self.settings,
            )
            # Clear ComfyUI execution cache before each generation to prevent duplicates
            try:
                import urllib.request as _req
                import json as _json
                free_data = _json.dumps({"unload_models": False, "free_memory": False}).encode()
                free_request = _req.Request(
                    f"{self.settings.comfyui_url}/free",
                    data=free_data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                _req.urlopen(free_request, timeout=10)
                logging.info("[Image] ComfyUI execution cache cleared via /free.")
            except Exception as free_exc:
                logging.warning(f"[Image] Failed to clear ComfyUI cache: {free_exc}")

            workflow = load_workflow_json(self.settings.comfyui_image_workflow)
            if not workflow:
                raise RuntimeError(
                    f"Image workflow not found: {self.settings.comfyui_image_workflow}"
                )
            # Generate at 1024x576 — Native 16:9 resolution, high detail and VRAM safe with --lowvram
            customized = customize_txt2img_workflow(workflow, image_prompt, width=1024, height=576)
            results = client.generate(customized)
            if not results:
                raise RuntimeError("ComfyUI returned no image.")
        finally:
            if orig is not None:
                os.environ["COMFYUI_AUTO_RELEASE_MEMORY"] = orig
            else:
                os.environ.pop("COMFYUI_AUTO_RELEASE_MEMORY", None)

        # Resize 1024x576 -> 1280x720 with lanczos + unsharp sharpening
        # (native 16:9 aspect ratio, no stretching)
        from PIL import Image as _Img, ImageFilter as _ImgF
        img = _Img.open(io.BytesIO(results[0])).convert("RGB")
        img_resized = img.resize((1280, 720), _Img.LANCZOS)
        img_sharp = img_resized.filter(_ImgF.UnsharpMask(radius=1.2, percent=100, threshold=3))
        buf = io.BytesIO()
        img_sharp.save(buf, format="PNG", optimize=False)
        logging.info("[Image] Generated 1024x576, resized+sharpened to 1280x720.")
        return buf.getvalue()


    # ------------------------------------------------------------------
    # Internal: Summary builder
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        raw_prompt: str,
        clip_results: list[ClipResult],
        final_video_path: Path,
        source_image_path: Path,
        total_time: float,
    ) -> str:
        successful = [r for r in clip_results if r.status == "SUCCESS"]
        failed = [r for r in clip_results if r.status == "FAIL"]
        total_duration = len(successful) * 5

        lines = [
            f"{'=' * 70}",
            f"VIDEO GENERATION SUMMARY",
            f"{'=' * 70}",
            f"Prompt         : {raw_prompt}",
            f"Source Image   : {source_image_path.name}",
            f"Final Video    : {final_video_path.name}",
            f"Video Duration : ~{total_duration}s ({len(successful)} clips × {ScriptEngine.CLIP_DURATION_SECONDS}s)",
            f"{'─' * 70}",
            f"Clips Generated: {len(successful)}/{len(clip_results)} succeeded",
        ]
        if failed:
            lines.append(f"Clips Failed   : {len(failed)}")

        for r in clip_results:
            icon = "✓" if r.status == "SUCCESS" else "✗"
            lines.append(
                f"  {icon} Scene {r.scene_number:02d} | {r.attempts} attempt(s) | "
                f"{r.generation_time_seconds:.0f}s | {r.status}"
            )

        lines += [
            f"{'─' * 70}",
            f"Total Pipeline Time: {total_time / 60:.1f} minutes ({total_time:.0f}s)",
            f"Output Location    : {final_video_path}",
            f"{'=' * 70}",
        ]
        return "\n".join(lines)

    def _fail_result(self, error: str, total_time: float) -> dict[str, Any]:
        return {
            "status": "FAIL",
            "error": error,
            "total_time_seconds": round(total_time, 1),
            "summary": f"PIPELINE FAILED: {error}",
        }


# ---------------------------------------------------------------------------
# Convenience runner — use this for test runs
# ---------------------------------------------------------------------------

def run_single_clip_test(
    raw_prompt: str,
    output_dir: Path,
    settings: Optional[Settings] = None,
) -> dict[str, Any]:
    """
    Convenience function for a single 6-second clip test run.
    Use this to validate image + video quality before long-form runs.
    """
    if settings is None:
        settings = Settings.from_environment()
    orch = LongFormOrchestrator(settings)
    return orch.run(
        raw_prompt=raw_prompt,
        target_seconds=6,
        output_dir=output_dir,
        job_name="single_clip_test",
    )


def run_long_form_test(
    raw_prompt: str,
    target_seconds: int,
    output_dir: Path,
    settings: Optional[Settings] = None,
) -> dict[str, Any]:
    """
    Convenience function for a long-form video run (30s, 60s, etc).
    """
    if settings is None:
        settings = Settings.from_environment()
    orch = LongFormOrchestrator(settings)
    return orch.run(
        raw_prompt=raw_prompt,
        target_seconds=target_seconds,
        output_dir=output_dir,
        job_name=f"longform_{target_seconds}s",
    )
