"""Local shadow patches for the 2D video pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]

external_root = os.getenv("KIDS_STUDIO_ORCHESTRATOR_ROOT", "").strip()
if external_root:
    candidate = Path(external_root).expanduser() / "src"
    if candidate.exists():
        __path__.append(str(candidate))
