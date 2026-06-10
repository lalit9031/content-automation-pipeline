"""Shadow package for the external 2D video pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]

external_root = os.getenv("KIDS_STUDIO_ORCHESTRATOR_ROOT", "").strip()
if external_root:
    candidate = Path(external_root).expanduser() / "src" / "video_pipeline"
    if candidate.exists():
        __path__.append(str(candidate))

from .asset_loader import (
    load_asset_bundle,
    load_character_bundle,
    load_dynamic_character_bundle,
)
from .frame_renderer import (
    compile_cinematic_story_frame,
    compose_story_frame,
    render_frame,
    render_dynamic_character_frame,
    render_story_frame,
)

__all__ = [
    "load_asset_bundle",
    "load_character_bundle",
    "load_dynamic_character_bundle",
    "compile_cinematic_story_frame",
    "compose_story_frame",
    "render_frame",
    "render_dynamic_character_frame",
    "render_story_frame",
]
