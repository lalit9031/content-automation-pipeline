from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image


def _resolve_orchestrator_root() -> Path:
    env_root = os.getenv("KIDS_STUDIO_ORCHESTRATOR_ROOT", "").strip()
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root).expanduser())

    cwd = Path.cwd()
    if (cwd / "assets").exists() and (cwd / "projects").exists():
        candidates.append(cwd)

    candidates.extend(
        [
            Path("/Volumes/Crucial X9/Mac/2D_Video/KidsStudio-Orchestrator"),
            Path("/Volumes/Crucial X9/Mac/2D_Video/story_studio"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return cwd


def _load_rgba(path: Path) -> Image.Image | None:
    if path.exists() and path.is_file():
        return Image.open(path).convert("RGBA")
    return None


def _is_valid_png(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".png" and not path.name.startswith("._")


def load_dynamic_character_bundle(character_folder_name: str, base_sprites_dir: str = "./assets/sprites") -> dict:
    """
    Load a character bundle that can be consumed by the 2D compiler.

    Supports:
    - legacy sprites with a single body.png
    - modular humans with base/face/hair/eyes/mouth/accessories
    - modular birds with separate wing assets
    """
    project_root = _resolve_orchestrator_root()
    sprites_dir = Path(base_sprites_dir)
    if not sprites_dir.is_absolute():
        sprites_dir = project_root / sprites_dir.as_posix().lstrip("./")

    target_path = sprites_dir / character_folder_name
    meta_file = target_path / "metadata.json"
    if not meta_file.exists():
        raise FileNotFoundError(
            f"Config file missing for asset bundle: [{character_folder_name}] at {meta_file}"
        )

    with open(meta_file, "r", encoding="utf-8") as f:
        meta_data = json.load(f)

    anchors = meta_data.get("anchors", {}) or {}
    assembly_mode = str(meta_data.get("assembly_mode", "legacy")).strip().lower()

    base_img = _load_rgba(target_path / "base.png") or _load_rgba(target_path / "body.png")
    if base_img is None:
        raise FileNotFoundError(
            f"base/body image missing for asset bundle: [{character_folder_name}]"
        )
    source_dimensions = tuple(meta_data.get("dimensions", list(base_img.size)))
    dimensions = tuple(base_img.size)

    bundle = {
        "asset_name": character_folder_name,
        "character_key": meta_data.get("character_key", character_folder_name.upper()),
        "source_path": str(target_path),
        "assembly_mode": assembly_mode,
        "dimensions": dimensions,
        "body_dimensions": dimensions,
        "source_dimensions": source_dimensions,
        "anchors": {
            "mouth_anchor_xy": tuple(anchors.get("mouth_anchor_xy", [0, 0])),
            "eyes_anchor_xy": tuple(anchors.get("eyes_anchor_xy", anchors.get("mouth_anchor_xy", [0, 0]))),
            "hair_anchor_xy": tuple(anchors.get("hair_anchor_xy", [0, 0])),
            "accessories_anchor_xy": tuple(anchors.get("accessories_anchor_xy", [0, 0])),
            "wing_left_anchor_xy": tuple(anchors.get("wing_left_anchor_xy", [0, 0])),
            "wing_right_anchor_xy": tuple(anchors.get("wing_right_anchor_xy", [0, 0])),
            "feather_pivot_xy": tuple(anchors.get("feather_pivot_xy", [0, 0])),
        },
        "mouth_anchor_xy": tuple(anchors.get("mouth_anchor_xy", [0, 0])),
        "eyes_anchor_xy": tuple(anchors.get("eyes_anchor_xy", anchors.get("mouth_anchor_xy", [0, 0]))),
        "hair_anchor_xy": tuple(anchors.get("hair_anchor_xy", [0, 0])),
        "accessories_anchor_xy": tuple(anchors.get("accessories_anchor_xy", [0, 0])),
        "wing_left_anchor_xy": tuple(anchors.get("wing_left_anchor_xy", [0, 0])),
        "wing_right_anchor_xy": tuple(anchors.get("wing_right_anchor_xy", [0, 0])),
        "feather_pivot_xy": tuple(anchors.get("feather_pivot_xy", [0, 0])),
        "body": base_img,
        "base": base_img,
        "layers": {"base": base_img},
        "mouths": {},
        "metadata": meta_data,
        "source_manifest": meta_file,
    }

    for layer_name in (
        # Modular human face/hair/eyes
        "face_base",
        "hair",
        "eyes",
        "eyes_blink",
        "accessories",
        # Bird wing layers
        "wing_left",
        "wing_right",
        "wings",
        "feathers",
        # 3/4 view rigging layers (pivot-based arm animation)
        "near_arm",
        "far_arm",
        "torso",
        "head",
    ):
        layer_img = _load_rgba(target_path / f"{layer_name}.png")
        if layer_img is not None:
            bundle["layers"][layer_name] = layer_img

    _ALL_LAYER_ALIASES = (
        "face_base", "hair", "eyes", "eyes_blink", "accessories",
        "wing_left", "wing_right", "wings", "feathers",
        "near_arm", "far_arm", "torso", "head",
    )
    for alias_name in _ALL_LAYER_ALIASES:
        if alias_name in bundle["layers"]:
            bundle[alias_name] = bundle["layers"][alias_name]

    # Also expose joint data at top level for easy access
    joints = meta_data.get("joints") or {}
    if joints:
        bundle["joints"] = {k: tuple(v) for k, v in joints.items()}
    gesture_limits = meta_data.get("gesture_limits") or {}
    if gesture_limits:
        bundle["gesture_limits"] = gesture_limits

    if "feathers" not in bundle["layers"]:
        feathers = _load_rgba(target_path / "feathers.png")
        if feathers is not None:
            bundle["layers"]["feathers"] = feathers
    bundle["feathers"] = bundle["layers"].get("feathers", Image.new("RGBA", (1, 1), (0, 0, 0, 0)))

    mouth_dir = target_path / "talk"
    if mouth_dir.exists():
        for file in sorted(mouth_dir.iterdir()):
            if _is_valid_png(file):
                shape_key = file.stem.upper()
                bundle["mouths"][shape_key] = Image.open(file).convert("RGBA")

    bundle["mouth_keys"] = sorted(bundle["mouths"].keys())
    bundle["neutral_mouth"] = "X" if "X" in bundle["mouths"] else (bundle["mouth_keys"][0] if bundle["mouth_keys"] else None)
    return bundle


def load_character_bundle(character_folder_name: str, base_sprites_dir: str = "./assets/sprites") -> dict:
    return load_dynamic_character_bundle(character_folder_name, base_sprites_dir)


def load_asset_bundle(character_folder_name: str, base_sprites_dir: str = "./assets/sprites") -> dict:
    return load_dynamic_character_bundle(character_folder_name, base_sprites_dir)


load_sprite_bundle = load_dynamic_character_bundle
load_bundle = load_dynamic_character_bundle
load_character_assets = load_dynamic_character_bundle
