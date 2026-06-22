"""Music Agent — a dedicated AI agent for generating music per section of the
content automation pipeline.

Capabilities
------------
1. Per-Scene Story Music Scoring
     Analyze a story script scene-by-scene, classify mood per scene,
     generate matching background music segments, and mix with narration.

2. Full-Song Generation
     Plan song structure (intro → verse → chorus → bridge → outro),
     write lyrics, generate instrumental beds, and orchestrate singing
     synthesis (RVC) or TTS-based vocals per section.

3. Pipeline Music Scheduling
     Schedule background music for video pipeline segments
     (intro → content → outro) with intelligent transitions,
     ducking, and crossfades.

Architecture
------------
    MusicAgent
        │
        ├── score_story_scenes()       → per-scene mood plan + audio
        ├── generate_full_song()       → structured song with sections
        ├── schedule_pipeline_music()   → intro / content / outro layout
        ├── generate_instrumental()    → wraps audio.py DSP / HF Spaces
        ├── mix_with_narration()       → wraps audio.py mixing agents
        └── generate_melody_guide()    → wraps melody_generator.py
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from content_pipeline.config import Settings
from content_pipeline.bots.audio import (
    STORY_SCORE_MOOD_STYLES,
    classify_story_mood,
    generate_layered_kids_instrumental,
    generate_instrumental_audio_track,
    generate_music_preview,
    mix_storytelling_with_adaptive_music,
    plan_story_music_segments,
    plan_story_music_segments_with_nim,
    smart_mix_storytelling_music_agent,
    SOUNDSCAPE_PRESETS,
)


# ---------------------------------------------------------------------------
#  DATA MODELS
# ---------------------------------------------------------------------------


@dataclass
class SceneMusicPlan:
    """Music plan for a single story scene."""
    index: int = 1
    scene_title: str = ""
    mood: str = "calm"
    style_description: str = ""
    duration_ms: int = 10000
    start_ms: int = 0
    text_preview: str = ""
    reason: str = ""


@dataclass
class SongSection:
    """A structural section of a song (intro, verse, chorus, etc.)."""
    section_type: str = "verse"           # intro, verse, chorus, bridge, outro, instrumental
    index: int = 1
    lyrics: str = ""
    duration_seconds: int = 16
    mood: str = "happy"
    bpm: int = 92
    style_description: str = ""
    audio_path: str = ""


@dataclass
class SongPlan:
    """Complete song structure plan."""
    title: str = ""
    language: str = "english"
    genre: str = "Pop"
    sections: list[SongSection] = field(default_factory=list)
    total_duration_seconds: int = 0
    singer_key: str = ""
    tempo_bpm: int = 92


@dataclass
class PipelineMusicSlot:
    """A music slot in the video pipeline timeline."""
    slot_type: str = "intro"              # intro, content, transition, outro
    index: int = 1
    mood: str = "calm"
    duration_seconds: int = 15
    style_description: str = ""
    fade_in_ms: int = 500
    fade_out_ms: int = 500
    crossfade_ms: int = 300
    duck_under_narration: bool = False


@dataclass
class PipelineMusicPlan:
    """Full pipeline music schedule."""
    slots: list[PipelineMusicSlot] = field(default_factory=list)
    total_duration_seconds: int = 0
    description: str = ""


# ---------------------------------------------------------------------------
#  MUSIC AGENT
# ---------------------------------------------------------------------------


class MusicAgent:
    """Dedicated AI agent for per-section music generation.

    Uses existing music tools from audio.py and melody_generator.py
    to provide a higher-level, structured API for planning and generating
    music per scene, song section, or pipeline slot.
    """

    # Standard pipeline layout presets
    PIPELINE_PRESETS: dict[str, list[dict[str, Any]]] = {
        "explainer": [
            {"slot_type": "intro",       "duration_seconds": 12, "mood": "calm",       "duck_under_narration": False},
            {"slot_type": "content",     "duration_seconds": 60, "mood": "happy",      "duck_under_narration": True},
            {"slot_type": "transition",  "duration_seconds": 6,  "mood": "magic",      "duck_under_narration": False},
            {"slot_type": "content",     "duration_seconds": 40, "mood": "adventure",  "duck_under_narration": True},
            {"slot_type": "outro",       "duration_seconds": 10, "mood": "calm",       "duck_under_narration": False},
        ],
        "kids_story": [
            {"slot_type": "intro",       "duration_seconds": 15, "mood": "calm",       "duck_under_narration": False},
            {"slot_type": "content",     "duration_seconds": 30, "mood": "happy",      "duck_under_narration": True},
            {"slot_type": "content",     "duration_seconds": 30, "mood": "adventure",  "duck_under_narration": True},
            {"slot_type": "content",     "duration_seconds": 20, "mood": "magic",      "duck_under_narration": True},
            {"slot_type": "outro",       "duration_seconds": 15, "mood": "calm",       "duck_under_narration": False},
        ],
        "cinematic": [
            {"slot_type": "intro",       "duration_seconds": 20, "mood": "suspense",   "duck_under_narration": False},
            {"slot_type": "content",     "duration_seconds": 40, "mood": "adventure",  "duck_under_narration": True},
            {"slot_type": "transition",  "duration_seconds": 8,  "mood": "magic",      "duck_under_narration": False},
            {"slot_type": "content",     "duration_seconds": 40, "mood": "sad",        "duck_under_narration": True},
            {"slot_type": "outro",       "duration_seconds": 15, "mood": "calm",       "duck_under_narration": False},
        ],
        "song_bed": [
            {"slot_type": "intro",       "duration_seconds": 8,  "mood": "calm",       "duck_under_narration": False},
            {"slot_type": "verse",       "duration_seconds": 16, "mood": "happy",      "duck_under_narration": False},
            {"slot_type": "chorus",      "duration_seconds": 16, "mood": "happy",      "duck_under_narration": False},
            {"slot_type": "verse",       "duration_seconds": 16, "mood": "happy",      "duck_under_narration": False},
            {"slot_type": "chorus",      "duration_seconds": 16, "mood": "happy",      "duck_under_narration": False},
            {"slot_type": "bridge",      "duration_seconds": 12, "mood": "calm",       "duck_under_narration": False},
            {"slot_type": "chorus",      "duration_seconds": 16, "mood": "happy",      "duck_under_narration": False},
            {"slot_type": "outro",       "duration_seconds": 10, "mood": "calm",       "duck_under_narration": False},
        ],
    }

    # Default song section templates
    SONG_SECTION_TEMPLATES: dict[str, dict[str, Any]] = {
        "intro": {
            "duration_seconds": 8,
            "mood": "calm",
            "bpm": 80,
            "style_description": "Pure instrumental. Soft opening intro with gentle pads and a hint of the main melody.",
        },
        "verse": {
            "duration_seconds": 16,
            "mood": "happy",
            "bpm": 92,
            "style_description": "Pure instrumental. Warm verse backing with light percussion, gentle chords, and space for vocals.",
        },
        "chorus": {
            "duration_seconds": 16,
            "mood": "happy",
            "bpm": 92,
            "style_description": "Pure instrumental. Energetic chorus with full instrumentation, bright melody, strong rhythm.",
        },
        "bridge": {
            "duration_seconds": 12,
            "mood": "calm",
            "bpm": 76,
            "style_description": "Pure instrumental. Emotional bridge section with softer dynamics, building tension before the final chorus.",
        },
        "outro": {
            "duration_seconds": 10,
            "mood": "calm",
            "bpm": 72,
            "style_description": "Pure instrumental. Gentle outro with slow fade, resolving the song peacefully.",
        },
        "instrumental": {
            "duration_seconds": 16,
            "mood": "adventure",
            "bpm": 92,
            "style_description": "Pure instrumental. Instrumental break featuring the main melody with full orchestral backing.",
        },
    }

    def __init__(
        self,
        settings: Settings,
        *,
        output_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.output_dir = (output_dir or settings.output_dir) / "music_agent"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._last_plan: dict[str, Any] = {}

    # -------------------------------------------------------------------
    #  1. PER-SCENE STORY MUSIC SCORING
    # -------------------------------------------------------------------

    def score_story_scenes(
        self,
        script: str,
        *,
        narration_path: Path | None = None,
        output_name: str = "story_score",
        max_segments: int = 8,
        use_nvidia_nim: bool = True,
        auto_mix: bool = True,
    ) -> dict[str, Any]:
        """Analyze a story script and generate per-scene background music.

        Args:
            script: Full story script text (Hindi or English).
            narration_path: Optional path to existing narration audio for mixing.
            output_name: Base name for output files.
            max_segments: Maximum number of music segments.
            use_nvidia_nim: Whether to try NVIDIA NIM for segment planning.
            auto_mix: Whether to mix the music segments with narration.

        Returns:
            Dict with scene_plan, audio_paths, mix_path, and metadata.
        """
        session_dir = self.output_dir / f"{output_name}_{self._session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)

        # 1. Plan music segments from script
        narration_duration_ms = 60000  # default 60s guess
        if narration_path and narration_path.exists():
            from pydub import AudioSegment
            narration_duration_ms = len(AudioSegment.from_file(str(narration_path)))

        plan: list[dict[str, Any]]
        if use_nvidia_nim and self.settings.nvidia_api_key:
            nim_plan = plan_story_music_segments_with_nim(
                script,
                narration_duration_ms,
                api_key=self.settings.nvidia_api_key,
                model=self.settings.nvidia_nim_model,
                max_segments=max_segments,
            )
            plan = nim_plan or plan_story_music_segments(
                script, narration_duration_ms, max_segments=max_segments
            )
        else:
            plan = plan_story_music_segments(
                script, narration_duration_ms, max_segments=max_segments
            )

        # 2. Generate music for each scene segment
        audio_paths: list[dict[str, Any]] = []
        for segment in plan:
            segment_seconds = max(6, math.ceil((segment["duration_ms"] + 1000) / 1000))
            segment_path = session_dir / (
                f"scene_{segment['index']:02d}_{segment['mood']}.mp3"
            )
            try:
                generate_layered_kids_instrumental(
                    segment_path,
                    duration_seconds=segment_seconds,
                    style_description=segment.get("style", ""),
                )
                audio_paths.append({
                    "index": segment["index"],
                    "mood": segment["mood"],
                    "duration_ms": segment["duration_ms"],
                    "path": str(segment_path),
                    "reason": segment.get("reason", ""),
                })
            except Exception as exc:
                audio_paths.append({
                    "index": segment["index"],
                    "mood": segment["mood"],
                    "error": str(exc),
                })

        # 3. Optionally mix with narration
        mix_path = None
        if auto_mix and narration_path and narration_path.exists():
            try:
                mixed_output = session_dir / f"{output_name}_mixed.mp3"
                mix_result = smart_mix_storytelling_music_agent(
                    narration_path=narration_path,
                    script=script,
                    output_path=mixed_output,
                    max_segments=max_segments,
                )
                mix_path = str(mix_result[0])
            except Exception as exc:
                mix_path = f"error: {exc}"

        # 4. Save scene plan JSON
        scene_plan = [
            SceneMusicPlan(
                index=s.get("index", i + 1),
                scene_title=f"Scene {s.get('index', i + 1)}",
                mood=s.get("mood", "calm"),
                style_description=s.get("style", ""),
                duration_ms=s.get("duration_ms", 10000),
                start_ms=s.get("start_ms", 0),
                text_preview=s.get("text_preview", "")[:120],
                reason=s.get("reason", ""),
            )
            for i, s in enumerate(plan)
        ]
        plan_path = session_dir / f"{output_name}_scene_plan.json"
        plan_path.write_text(
            json.dumps(
                {"scenes": [asdict(sp) for sp in scene_plan], "audio_paths": audio_paths},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = {
            "session_dir": str(session_dir),
            "scene_plan": [asdict(sp) for sp in scene_plan],
            "audio_paths": audio_paths,
            "mix_path": mix_path,
            "plan_path": str(plan_path),
        }
        self._last_plan = result
        return result

    # -------------------------------------------------------------------
    #  2. FULL-SONG GENERATION
    # -------------------------------------------------------------------

    def generate_full_song(
        self,
        *,
        title: str = "Untitled Song",
        lyrics: str = "",
        language: str = "english",
        genre: str = "Pop",
        sections: list[str] | None = None,
        singer_key: str = "",
        tempo_bpm: int = 92,
        output_name: str = "full_song",
        generate_instrumentals: bool = True,
        generate_vocals: bool = False,
    ) -> dict[str, Any]:
        """Generate a complete song with per-section music.

        Args:
            title: Song title.
            lyrics: Full lyrics (can be empty for instrumental only).
            language: Language of the song.
            genre: Music genre (Pop, Kids, Cinematic, etc.).
            sections: Ordered list of section types: intro, verse, chorus,
                      bridge, outro, instrumental. Defaults to standard pop.
            singer_key: Singer model key for RVC vocal synthesis.
            tempo_bpm: Base tempo in BPM.
            output_name: Base name for output files.
            generate_instrumentals: Whether to generate instrumental beds.
            generate_vocals: Whether to attempt vocal synthesis (RVC).

        Returns:
            Dict with song_plan, audio_paths, and metadata.
        """
        session_dir = self.output_dir / f"{output_name}_{self._session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)

        # 1. Resolve song structure
        if not sections:
            sections = ["intro", "verse", "chorus", "verse", "chorus", "bridge", "chorus", "outro"]

        # 2. Split lyrics into sections (by blank lines or evenly)
        lyric_lines = [line.strip() for line in lyrics.split("\n") if line.strip()]
        lyric_sections: list[str] = []
        if lyric_lines:
            # Try to split lyrics by blank-line-delimited stanzas
            raw_stanzas = re.split(r"\n\s*\n", lyrics.strip())
            raw_stanzas = [s.strip() for s in raw_stanzas if s.strip()]
            if len(raw_stanzas) >= len(sections):
                lyric_sections = raw_stanzas[:len(sections)]
            elif len(raw_stanzas) > 0:
                # Distribute lyrics evenly across sections
                per_section = max(1, len(lyric_lines) // len(sections))
                for i in range(len(sections)):
                    start = i * per_section
                    end = start + per_section if i < len(sections) - 1 else len(lyric_lines)
                    lyric_sections.append(" ".join(lyric_lines[start:end]))
            else:
                lyric_sections = [""] * len(sections)
        else:
            lyric_sections = [""] * len(sections)

        # 3. Build song sections
        song_sections: list[SongSection] = []
        for i, section_type in enumerate(sections):
            template = self.SONG_SECTION_TEMPLATES.get(section_type, self.SONG_SECTION_TEMPLATES["verse"])
            section_lyrics = lyric_sections[i] if i < len(lyric_sections) else ""
            section_bpm = tempo_bpm
            if section_type in ("bridge", "intro", "outro"):
                section_bpm = max(60, tempo_bpm - 12)

            song_sections.append(SongSection(
                section_type=section_type,
                index=i + 1,
                lyrics=section_lyrics,
                duration_seconds=template["duration_seconds"],
                mood=template["mood"],
                bpm=section_bpm,
                style_description=template["style_description"],
            ))

        # 4. Generate instrumental beds per section
        audio_paths: list[dict[str, Any]] = []
        if generate_instrumentals:
            for sec in song_sections:
                sec_path = session_dir / f"{sec.section_type}_{sec.index:02d}.mp3"
                try:
                    generate_layered_kids_instrumental(
                        sec_path,
                        duration_seconds=sec.duration_seconds,
                        bpm=sec.bpm,
                        style_description=(
                            f"{sec.style_description} Genre: {genre}, Language: {language}."
                        ),
                    )
                    sec.audio_path = str(sec_path)
                    audio_paths.append({
                        "section": sec.section_type,
                        "index": sec.index,
                        "path": str(sec_path),
                        "duration_seconds": sec.duration_seconds,
                        "mood": sec.mood,
                    })
                except Exception as exc:
                    audio_paths.append({
                        "section": sec.section_type,
                        "index": sec.index,
                        "error": str(exc),
                    })

        # 5. Optionally synthesize vocals via RVC pipeline
        vocal_paths: list[dict[str, Any]] = []
        if generate_vocals and singer_key:
            for sec in song_sections:
                if sec.lyrics and sec.audio_path:
                    try:
                        from content_pipeline.bots.singing_synthesis import (
                            orchestrate_dynamic_vocal_pipeline,
                        )
                        singer_prefix, pitch_shift = orchestrate_dynamic_vocal_pipeline(
                            singer_key, sec.lyrics
                        )
                        vocal_paths.append({
                            "section": sec.section_type,
                            "index": sec.index,
                            "singer": singer_prefix,
                            "pitch_shift": pitch_shift,
                            "note": "Vocal synthesis requires RVC worker environment setup",
                        })
                    except Exception as exc:
                        vocal_paths.append({
                            "section": sec.section_type,
                            "index": sec.index,
                            "error": str(exc),
                        })

        # 6. Attempt edge-tts vocal fallback for non-RVC sections
        if generate_vocals and not vocal_paths:
            for sec in song_sections:
                if sec.lyrics:
                    try:
                        tts_path = session_dir / f"{sec.section_type}_{sec.index:02d}_vocal.mp3"
                        generate_indian_voiceover(
                            sec.lyrics,
                            tts_path,
                            voice="en-IN-PrabhatNeural",
                        )
                        vocal_paths.append({
                            "section": sec.section_type,
                            "index": sec.index,
                            "path": str(tts_path),
                            "method": "edge-tts",
                        })
                    except Exception as exc:
                        vocal_paths.append({
                            "section": sec.section_type,
                            "index": sec.index,
                            "error": str(exc),
                        })

        # 7. Build song plan and save
        total_duration = sum(s.duration_seconds for s in song_sections)
        song_plan = SongPlan(
            title=title,
            language=language,
            genre=genre,
            sections=song_sections,
            total_duration_seconds=total_duration,
            singer_key=singer_key,
            tempo_bpm=tempo_bpm,
        )
        plan_path = session_dir / f"{output_name}_plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "title": title,
                    "language": language,
                    "genre": genre,
                    "total_duration_seconds": total_duration,
                    "sections": [asdict(s) for s in song_sections],
                    "instrumental_paths": audio_paths,
                    "vocal_paths": vocal_paths,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = {
            "session_dir": str(session_dir),
            "song_plan": asdict(song_plan),
            "instrumental_paths": audio_paths,
            "vocal_paths": vocal_paths,
            "plan_path": str(plan_path),
        }
        self._last_plan = result
        return result

    # -------------------------------------------------------------------
    #  3. PIPELINE MUSIC SCHEDULING
    # -------------------------------------------------------------------

    def schedule_pipeline_music(
        self,
        *,
        preset: str = "kids_story",
        custom_slots: list[PipelineMusicSlot] | None = None,
        output_name: str = "pipeline_music",
        narration_path: Path | None = None,
        script: str = "",
        duck_under_narration: bool = True,
    ) -> dict[str, Any]:
        """Schedule and generate background music for a video pipeline.

        Args:
            preset: Name of a pipeline preset ('kids_story', 'explainer',
                    'cinematic', 'song_bed') or 'custom' for custom_slots.
            custom_slots: Custom slot list (used when preset='custom').
            output_name: Base name for output files.
            narration_path: Optional narration audio for timing/mixing.
            script: Story script for mood detection per slot.
            duck_under_narration: Whether to duck music under narration.

        Returns:
            Dict with pipeline_plan, slot_paths, mixed_path, metadata.
        """
        session_dir = self.output_dir / f"{output_name}_{self._session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)

        # 1. Resolve slots
        slots: list[PipelineMusicSlot]
        if preset != "custom" and custom_slots is None:
            raw_slots = self.PIPELINE_PRESETS.get(preset, self.PIPELINE_PRESETS["kids_story"])
            slots = [
                PipelineMusicSlot(
                    slot_type=s["slot_type"],
                    index=i + 1,
                    mood=s.get("mood", "calm"),
                    duration_seconds=s.get("duration_seconds", 15),
                    duck_under_narration=s.get("duck_under_narration", duck_under_narration),
                )
                for i, s in enumerate(raw_slots)
            ]
        elif custom_slots is not None:
            slots = custom_slots
        else:
            slots = [
                PipelineMusicSlot(slot_type="intro", index=1, duration_seconds=15),
                PipelineMusicSlot(slot_type="content", index=2, duration_seconds=60, duck_under_narration=True),
                PipelineMusicSlot(slot_type="outro", index=3, duration_seconds=10),
            ]

        # 2. Auto-detect moods from script if script is provided
        if script:
            script_units = [
                unit.strip()
                for unit in re.split(r"(?<=[।.!?])\s+|\n+", script)
                if unit.strip()
            ]
            for i, slot in enumerate(slots):
                if slot.slot_type == "content" and script_units:
                    unit_index = min(i, len(script_units) - 1)
                    mood, _reason = classify_story_mood(script_units[unit_index])
                    slot.mood = mood

        # 3. Generate music for each slot
        slot_paths: list[dict[str, Any]] = []
        for slot in slots:
            slot_dir = session_dir / "slots"
            slot_dir.mkdir(parents=True, exist_ok=True)
            slot_path = slot_dir / f"{slot.slot_type}_{slot.index:02d}_{slot.mood}.mp3"

            style = STORY_SCORE_MOOD_STYLES.get(slot.mood, STORY_SCORE_MOOD_STYLES["calm"])
            try:
                generate_layered_kids_instrumental(
                    slot_path,
                    duration_seconds=max(6, slot.duration_seconds),
                    style_description=style,
                )
                slot_paths.append({
                    "slot_type": slot.slot_type,
                    "index": slot.index,
                    "mood": slot.mood,
                    "path": str(slot_path),
                    "duration_seconds": slot.duration_seconds,
                })
            except Exception as exc:
                slot_paths.append({
                    "slot_type": slot.slot_type,
                    "index": slot.index,
                    "error": str(exc),
                })

        # 4. Optionally mix with narration
        mixed_path = None
        if narration_path and narration_path.exists() and duck_under_narration:
            try:
                mixed_output = session_dir / f"{output_name}_mixed.mp3"
                mix_storytelling_with_adaptive_music(
                    narration_path=narration_path,
                    script=script or output_name,
                    output_path=mixed_output,
                    max_segments=len(slots),
                )
                mixed_path = str(mixed_output)
            except Exception as exc:
                mixed_path = f"error: {exc}"

        # 5. Save pipeline plan
        total_duration = sum(s.duration_seconds for s in slots)
        pipeline_plan = PipelineMusicPlan(
            slots=slots,
            total_duration_seconds=total_duration,
            description=f"Pipeline preset: {preset}",
        )
        plan_path = session_dir / f"{output_name}_pipeline_plan.json"
        plan_path.write_text(
            json.dumps(
                {
                    "preset": preset,
                    "total_duration_seconds": total_duration,
                    "slots": [asdict(s) for s in slots],
                    "slot_paths": slot_paths,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = {
            "session_dir": str(session_dir),
            "pipeline_plan": asdict(pipeline_plan),
            "slot_paths": slot_paths,
            "mixed_path": mixed_path,
            "plan_path": str(plan_path),
        }
        self._last_plan = result
        return result

    # -------------------------------------------------------------------
    #  4. STANDALONE GENERATION TOOLS
    # -------------------------------------------------------------------

    def generate_instrumental(
        self,
        output_path: Path,
        *,
        duration_seconds: int = 90,
        style_description: str = "",
        mood: str = "calm",
        bpm: int = 92,
        use_hf_space: bool = False,
        genre: str = "Pop",
    ) -> Path:
        """Generate an instrumental track using best available engine.

        Uses local DSP by default. Falls back to HF Space if use_hf_space=True.
        """
        if use_hf_space and self.settings.hf_token:
            return generate_instrumental_audio_track(
                output_path,
                style_description=style_description or STORY_SCORE_MOOD_STYLES.get(mood, ""),
                hf_token=self.settings.hf_token,
                genre=genre,
                duration_seconds=duration_seconds,
                force_local=False,
            )
        return generate_layered_kids_instrumental(
            output_path,
            duration_seconds=duration_seconds,
            bpm=bpm,
            style_description=style_description or STORY_SCORE_MOOD_STYLES.get(mood, ""),
        )

    def generate_preview(
        self,
        output_path: Path,
        *,
        mood: str = "cinematic",
        duration_seconds: int = 8,
    ) -> Path:
        """Generate a short music preview (sine-wave based)."""
        return generate_music_preview(output_path, mood, duration_seconds=duration_seconds)

    def generate_melody_guide(
        self,
        duration_seconds: float,
        *,
        tempo_bpm: int = 80,
        gender: str = "Male",
        speech_path: Path | None = None,
        output_name: str = "melody_guide",
    ) -> dict[str, Any]:
        """Generate an Indian classical melody guide for RVC pitch reference."""
        from content_pipeline.bots.melody_generator import generate_synthetic_melody_guide

        session_dir = self.output_dir / f"{output_name}_{self._session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        output_path = session_dir / f"{output_name}.wav"

        result_path = generate_synthetic_melody_guide(
            duration_seconds=duration_seconds,
            tempo_bpm=tempo_bpm,
            output_path=str(output_path),
            gender=gender,
            speech_path=str(speech_path) if speech_path else None,
        )
        return {
            "path": result_path,
            "duration_seconds": duration_seconds,
            "tempo_bpm": tempo_bpm,
            "gender": gender,
        }

    def mix_with_narration(
        self,
        narration_path: Path,
        script: str,
        output_path: Path,
        *,
        max_segments: int = 6,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        """Mix generated music with narration audio using the smart mixing agent."""
        final_path, final_plan, report = smart_mix_storytelling_music_agent(
            narration_path=narration_path,
            script=script,
            output_path=output_path,
            max_segments=max_segments,
            max_attempts=max_attempts,
        )
        return {
            "mix_path": str(final_path),
            "plan": final_plan,
            "report": report,
        }

    # -------------------------------------------------------------------
    #  UTILITY
    # -------------------------------------------------------------------

    def get_last_plan(self) -> dict[str, Any]:
        """Return the most recent plan."""
        return self._last_plan

    def list_presets(self) -> dict[str, list[dict[str, Any]]]:
        """Return available pipeline presets."""
        return {
            name: slots for name, slots in self.PIPELINE_PRESETS.items()
        }

    def list_presets_keys(self) -> list[str]:
        """Return available preset names."""
        return list(self.PIPELINE_PRESETS.keys())

    def list_soundscape_presets(self) -> dict[str, dict[str, Any]]:
        """Return available soundscape style presets from audio.py."""
        return dict(SOUNDSCAPE_PRESETS)

    def status(self) -> dict[str, Any]:
        """Return agent status summary."""
        return {
            "agent": "MusicAgent",
            "session_id": self._session_id,
            "output_dir": str(self.output_dir),
            "available_presets": self.list_presets_keys(),
            "available_soundscapes": list(SOUNDSCAPE_PRESETS.keys()),
            "has_last_plan": bool(self._last_plan),
        }
