from __future__ import annotations

import math
from typing import Any

from PIL import Image, ImageDraw, ImageFilter


def _resample() -> int:
    return getattr(Image, "Resampling", Image).LANCZOS


def _scale_size(size: tuple[int, int], scale: float) -> tuple[int, int]:
    width = max(1, int(round(size[0] * scale)))
    height = max(1, int(round(size[1] * scale)))
    return width, height


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _paste(canvas: Image.Image, layer: Image.Image | None, x: float, y: float) -> None:
    if layer is None:
        return
    if layer.mode != "RGBA":
        layer = layer.convert("RGBA")
    canvas.paste(layer, (int(round(x)), int(round(y))), layer)


def _paste_centered(canvas: Image.Image, layer: Image.Image | None, anchor_x: float, anchor_y: float) -> None:
    if layer is None:
        return
    if layer.mode != "RGBA":
        layer = layer.convert("RGBA")
    alpha = layer.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return
    crop = layer.crop(bbox)
    crop_center_x = bbox[0] + (crop.width / 2.0)
    crop_center_y = bbox[1] + (crop.height / 2.0)
    x = int(round(anchor_x - crop_center_x))
    y = int(round(anchor_y - crop_center_y))
    canvas.paste(crop, (x, y), crop)


def _resize(layer: Image.Image | None, size: tuple[int, int]) -> Image.Image | None:
    if layer is None:
        return None
    if layer.size == size:
        return layer
    return layer.resize(size, _resample())


def _get_actor_value(actor: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in actor and actor[key] not in (None, ""):
        return actor[key]
    bundle = actor.get("bundle") or {}
    if key in bundle and bundle[key] not in (None, ""):
        return bundle[key]
    return default


def _get_anchor(bundle: dict[str, Any], actor: dict[str, Any], name: str) -> tuple[float, float]:
    alias_map = {
        "mouth_anchor_xy": ("mouth_anchor_coordinates", "mouth_anchor", "mouth_pos"),
        "eyes_anchor_xy": ("eyes_anchor_coordinates", "eyes_anchor"),
        "hair_anchor_xy": ("hair_anchor_coordinates", "hair_anchor"),
        "accessories_anchor_xy": ("accessories_anchor_coordinates", "accessories_anchor"),
        "wing_left_anchor_xy": ("wing_left_anchor_coordinates", "wing_left_anchor"),
        "wing_right_anchor_xy": ("wing_right_anchor_coordinates", "wing_right_anchor"),
        "feather_pivot_xy": ("feather_pivot", "feather_pivot_coordinates"),
    }

    actor_anchor = actor.get(f"{name}_xy")
    if actor_anchor:
        return float(actor_anchor[0]), float(actor_anchor[1])
    for alias in alias_map.get(name, ()):
        actor_anchor = actor.get(alias)
        if actor_anchor:
            return float(actor_anchor[0]), float(actor_anchor[1])
    source_dimensions = bundle.get("source_dimensions") or bundle.get("metadata", {}).get("dimensions")
    target_dimensions = bundle.get("dimensions") or bundle.get("body_dimensions") or bundle.get("body", {}).get("size")

    def _scale_anchor(anchor: tuple[float, float]) -> tuple[float, float]:
        if (
            isinstance(source_dimensions, (tuple, list))
            and len(source_dimensions) >= 2
            and isinstance(target_dimensions, (tuple, list))
            and len(target_dimensions) >= 2
            and float(source_dimensions[0]) > 0
            and float(source_dimensions[1]) > 0
        ):
            sx = float(target_dimensions[0]) / float(source_dimensions[0])
            sy = float(target_dimensions[1]) / float(source_dimensions[1])
            return float(anchor[0]) * sx, float(anchor[1]) * sy
        return float(anchor[0]), float(anchor[1])

    if "anchors" in bundle and isinstance(bundle["anchors"], dict) and name in bundle["anchors"]:
        anchor = bundle["anchors"][name]
        return _scale_anchor((float(anchor[0]), float(anchor[1])))
    bundle_anchor = bundle.get(name)
    if isinstance(bundle_anchor, (tuple, list)) and len(bundle_anchor) >= 2:
        return _scale_anchor((float(bundle_anchor[0]), float(bundle_anchor[1])))
    for alias in alias_map.get(name, ()):
        bundle_anchor = bundle.get(alias)
        if isinstance(bundle_anchor, (tuple, list)) and len(bundle_anchor) >= 2:
            return _scale_anchor((float(bundle_anchor[0]), float(bundle_anchor[1])))
    return 0.0, 0.0


def _choose_mouth_key(bundle: dict[str, Any], actor: dict[str, Any], frame_index: int, fps: int) -> str | None:
    mouths = bundle.get("mouths") or {}
    if not mouths:
        return None

    direct = (
        actor.get("mouth_state")
        or actor.get("mouth_key")
        or actor.get("phoneme")
        or actor.get("mouth")
        or actor.get("animation_mouth")
    )
    if isinstance(direct, str):
        key = direct.strip().upper()
        if key in mouths:
            return key

    animation_state = str(actor.get("animation_state", "")).lower()
    talking = "talk" in animation_state or "lip" in animation_state or "speech" in animation_state or actor.get("is_talking")
    if not talking:
        neutral = bundle.get("neutral_mouth")
        if isinstance(neutral, str) and neutral in mouths:
            return neutral

    ordered = [key for key in ("X", "A", "B", "C", "D", "E", "F", "G", "H") if key in mouths]
    if not ordered:
        ordered = sorted(mouths.keys())
    if not ordered:
        return None

    if len(ordered) == 1:
        return ordered[0]

    tick = max(1, fps // 6)
    index = (frame_index // tick) % len(ordered)
    return ordered[index]


def _mouth_scale(actor: dict[str, Any], bundle: dict[str, Any]) -> float:
    scale = float(
        actor.get("curr_scale")
        or actor.get("scale")
        or actor.get("target_scale")
        or actor.get("display_scale")
        or 1.0
    )
    if str(bundle.get("assembly_mode", "")).lower() == "modular_human":
        return max(0.4, min(1.15, scale * 0.58))
    return max(0.4, min(1.15, scale * 0.52))


def _sample_background_palette(bg_img: Image.Image) -> tuple[int, int, int]:
    sample = bg_img.convert("RGBA")
    # Focus on the lower half where warm sunrise light and environment color are strongest.
    crop = sample.crop((0, int(sample.height * 0.35), sample.width, sample.height))
    pixels = list(crop.getdata())
    if not pixels:
        return (190, 170, 150)
    total_r = total_g = total_b = count = 0
    for r, g, b, a in pixels:
        if a <= 10:
            continue
        total_r += r
        total_g += g
        total_b += b
        count += 1
    if not count:
        return (190, 170, 150)
    return (
        int(total_r / count),
        int(total_g / count),
        int(total_b / count),
    )


def _apply_ambient_light_match(character_canvas: Image.Image, bg_img: Image.Image, bundle: dict[str, Any], actor: dict[str, Any]) -> Image.Image:
    assembly_mode = str(bundle.get("assembly_mode", "legacy")).lower()
    if assembly_mode not in {"modular_human", "modular_bird"}:
        return character_canvas

    bg_r, bg_g, bg_b = _sample_background_palette(bg_img)
    warmth = _clamp((bg_r - bg_b) / 170.0, 0.0, 1.0)
    glow = _clamp((bg_r + bg_g + bg_b) / 765.0, 0.0, 1.0)
    strength = 0.08 + (0.10 * glow) + (0.08 * warmth)
    if "talk" in str(actor.get("animation_state", "")).lower() or actor.get("is_talking"):
        strength += 0.02
    strength = _clamp(strength, 0.08, 0.22)

    # Bias toward warm sunrise / sunset tones so the puppet feels like it belongs in the scene.
    tint_r = min(255, int(bg_r * 1.04 + 10))
    tint_g = min(255, int(bg_g * 0.96 + 6))
    tint_b = min(255, int(bg_b * 0.90 + 2))
    tint_layer = Image.new("RGBA", character_canvas.size, (tint_r, tint_g, tint_b, int(round(255 * strength))))
    return Image.alpha_composite(character_canvas, tint_layer)


def _apply_face_mouth_cover(character_canvas: Image.Image, bundle: dict[str, Any], actor: dict[str, Any]) -> Image.Image:
    assembly_mode = str(bundle.get("assembly_mode", "legacy")).lower()
    if assembly_mode != "modular_human":
        return character_canvas

    mouth_x, mouth_y = _get_anchor(bundle, actor, "mouth_anchor_xy")
    cover = Image.new("RGBA", character_canvas.size, (0, 0, 0, 0))
    mask = Image.new("L", character_canvas.size, 0)
    draw = ImageDraw.Draw(cover)
    mask_draw = ImageDraw.Draw(mask)
    skin_tone = _sample_color(bundle.get("face_base") or bundle.get("body"), (236, 204, 177, 255))

    cover_w = max(14, int(round(character_canvas.width * 0.11)))
    cover_h = max(10, int(round(character_canvas.height * 0.055)))
    left = int(round(mouth_x - (cover_w / 2.0)))
    top = int(round(mouth_y - (cover_h * 0.78)))
    right = left + cover_w
    bottom = top + cover_h
    draw.rounded_rectangle(
        (left, top, right, bottom),
        radius=max(6, int(round(cover_h * 0.40))),
        fill=(skin_tone[0], skin_tone[1], skin_tone[2], 175),
    )
    # A soft mask keeps the cover invisible as a patch instead of a hard sticker.
    mask_draw.rounded_rectangle(
        (left, top, right, bottom),
        radius=max(6, int(round(cover_h * 0.40))),
        fill=175,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(1, int(round(cover_h * 0.18)))))
    cover.putalpha(mask)
    return Image.alpha_composite(character_canvas, cover)


def _build_character_shadow(
    character_canvas: Image.Image,
    actor: dict[str, Any],
    bundle: dict[str, Any],
    frame_index: int,
    fps: int,
) -> Image.Image | None:
    placement_mode = str(
        actor.get("placement_mode")
        or actor.get("position_mode")
        or actor.get("anchor_mode")
        or bundle.get("assembly_mode", "legacy")
    ).lower()
    if placement_mode not in {"ground", "grounded", "bottom", "bottom_center", "modular_human"}:
        return None

    width = max(40, int(round(character_canvas.width * 0.55)))
    height = max(10, int(round(character_canvas.height * 0.07)))
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shadow)
    alpha = int(70 if str(bundle.get("assembly_mode", "")).lower() == "modular_bird" else 85)
    if "talk" in str(actor.get("animation_state", "")).lower():
        alpha = max(55, alpha - 10)
    draw.ellipse((0, 0, width - 1, height - 1), fill=(0, 0, 0, alpha))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(2, int(round(height * 0.55)))))
    return shadow


def _apply_body_realism(
    character_canvas: Image.Image,
    actor: dict[str, Any],
    bundle: dict[str, Any],
    frame_index: int,
    fps: int,
) -> Image.Image:
    assembly_mode = str(bundle.get("assembly_mode", "legacy")).lower()
    phase = float(actor.get("motion_phase", 0.0))
    talking = "talk" in str(actor.get("animation_state", "")).lower() or "lip" in str(actor.get("animation_state", "")).lower() or actor.get("is_talking")

    if assembly_mode == "modular_human":
        sway = math.sin((frame_index / max(1.0, fps * 0.9)) + phase) * (0.65 if talking else 0.35)
        breathing = 1.0 + (0.008 if talking else 0.004) * math.sin((frame_index / max(1.0, fps * 0.55)) + phase)
        if abs(sway) > 0.01 or abs(breathing - 1.0) > 0.0005:
            scaled_w = max(1, int(round(character_canvas.width * breathing)))
            scaled_h = max(1, int(round(character_canvas.height * (1.0 + (0.006 if talking else 0.003) * math.sin((frame_index / max(1.0, fps * 0.65)) + phase)))))
            transformed = character_canvas.resize((scaled_w, scaled_h), _resample())
            rotated = transformed.rotate(sway, resample=Image.Resampling.BICUBIC, expand=False, center=(transformed.width / 2.0, transformed.height / 2.0))
            if rotated.size != character_canvas.size:
                result = Image.new("RGBA", character_canvas.size, (0, 0, 0, 0))
                x = (result.width - rotated.width) // 2
                y = (result.height - rotated.height) // 2
                _paste(result, rotated, x, y)
                return result
            return rotated

    if assembly_mode == "modular_bird":
        sway = math.sin((frame_index / max(1.0, fps * 0.8)) + phase) * (1.0 if talking else 0.55)
        if abs(sway) > 0.01:
            return character_canvas.rotate(sway, resample=Image.Resampling.BICUBIC, expand=False, center=(character_canvas.width / 2.0, character_canvas.height / 2.0))

    return character_canvas


def _sample_color(layer: Image.Image | None, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if layer is None:
        return fallback
    rgba = layer.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return fallback
    sample = rgba.crop(bbox)
    pixels = list(sample.getdata())
    total = [0, 0, 0, 0]
    count = 0
    for r, g, b, a in pixels:
        if a == 0:
            continue
        total[0] += r
        total[1] += g
        total[2] += b
        total[3] += a
        count += 1
    if count == 0:
        return fallback
    return tuple(int(total[i] / count) for i in range(4))


def _draw_soft_limb(draw: ImageDraw.ImageDraw, start_xy: tuple[float, float], end_xy: tuple[float, float], width: int, fill: tuple[int, int, int, int]) -> None:
    draw.line([start_xy, end_xy], fill=fill, width=width)
    sx, sy = start_xy
    ex, ey = end_xy
    radius = max(2, width // 2)
    draw.ellipse((sx - radius, sy - radius, sx + radius, sy + radius), fill=fill)
    draw.ellipse((ex - radius, ey - radius, ex + radius, ey + radius), fill=fill)


def _build_human_arm_layer(
    character_canvas: Image.Image,
    bundle: dict[str, Any],
    actor: dict[str, Any],
    frame_index: int,
    fps: int,
) -> Image.Image | None:
    if str(bundle.get("assembly_mode", "")).lower() != "modular_human":
        return None

    base = bundle.get("layers", {}).get("base") or bundle.get("body")
    if base is None:
        return None

    phase = float(actor.get("motion_phase", 0.0))
    talking = "talk" in str(actor.get("animation_state", "")).lower() or "lip" in str(actor.get("animation_state", "")).lower() or actor.get("is_talking")
    body_tone = _sample_color(bundle.get("body"), (244, 210, 185, 255))
    shirt_tone = _sample_color(base, (70, 132, 250, 255))
    skin = (body_tone[0], body_tone[1], body_tone[2], 255)

    overlay = Image.new("RGBA", character_canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    shoulder_y = int(round(character_canvas.height * 0.34))
    torso_top = int(round(character_canvas.height * 0.28))
    torso_mid = int(round(character_canvas.width * 0.5))
    arm_length = max(1, int(round(character_canvas.height * (0.22 if talking else 0.20))))
    forearm_length = max(1, int(round(character_canvas.height * 0.14)))
    hand_radius = max(3, int(round(character_canvas.height * 0.02)))
    arm_width = max(4, int(round(character_canvas.width * 0.04)))
    elbow_width = max(3, int(round(arm_width * 0.82)))

    sway = math.sin((frame_index / max(1.0, fps * 0.9)) + phase)
    lift = math.sin((frame_index / max(1.0, fps * 0.7)) + phase + 0.9)
    talk_lift = 1.0 if talking else 0.0

    left_shoulder = (torso_mid - character_canvas.width * 0.18, shoulder_y)
    right_shoulder = (torso_mid + character_canvas.width * 0.18, shoulder_y)

    left_elbow = (
        left_shoulder[0] - character_canvas.width * (0.04 + 0.02 * sway),
        shoulder_y + arm_length * (0.55 - 0.06 * lift),
    )
    right_elbow = (
        right_shoulder[0] + character_canvas.width * (0.04 + 0.02 * sway),
        shoulder_y + arm_length * (0.55 + 0.06 * lift),
    )

    left_hand = (
        left_elbow[0] - character_canvas.width * 0.02,
        left_elbow[1] + forearm_length * (0.95 - 0.06 * talk_lift),
    )
    right_hand = (
        right_elbow[0] + character_canvas.width * 0.02,
        right_elbow[1] + forearm_length * (0.95 + 0.06 * talk_lift),
    )

    _draw_soft_limb(draw, left_shoulder, left_elbow, arm_width, skin)
    _draw_soft_limb(draw, left_elbow, left_hand, elbow_width, skin)
    _draw_soft_limb(draw, right_shoulder, right_elbow, arm_width, skin)
    _draw_soft_limb(draw, right_elbow, right_hand, elbow_width, skin)

    for hx, hy in (left_hand, right_hand):
        draw.ellipse((hx - hand_radius, hy - hand_radius, hx + hand_radius, hy + hand_radius), fill=skin)

    # Give the shirt edge a tiny overpaint so the arms feel embedded instead of detached.
    draw.rounded_rectangle(
        (
            torso_mid - character_canvas.width * 0.21,
            torso_top,
            torso_mid + character_canvas.width * 0.21,
            int(round(character_canvas.height * 0.64)),
        ),
        radius=int(round(character_canvas.width * 0.08)),
        outline=shirt_tone,
        width=max(1, int(round(character_canvas.width * 0.018))),
    )
    return overlay


def _apply_close_up_crop(frame_canvas: Image.Image, manifest_config: dict, canvas_w: int, canvas_h: int) -> Image.Image:
    camera_mode = str(
        manifest_config.get("active_camera_angle")
        or manifest_config.get("camera_mode")
        or manifest_config.get("shot_type")
        or ""
    ).upper()
    focus = (
        manifest_config.get("camera_focus_target_xy")
        or manifest_config.get("camera_focus_xy")
        or manifest_config.get("camera_target_xy")
    )
    if camera_mode != "CLOSE_UP" or not focus:
        return frame_canvas

    try:
        target_focus_x, target_focus_y = float(focus[0]), float(focus[1])
    except Exception:
        return frame_canvas

    crop_w = max(1, int(canvas_w * 0.72))
    crop_h = max(1, int(canvas_h * 0.72))
    x1 = max(0, min(int(target_focus_x - (crop_w / 2.0)), canvas_w - crop_w))
    y1 = max(0, min(int(target_focus_y - (crop_h / 2.0)), canvas_h - crop_h))
    cropped_view = frame_canvas.crop((x1, y1, x1 + crop_w, y1 + crop_h))
    return cropped_view.resize((canvas_w, canvas_h), _resample())


def _needs_blink(actor: dict[str, Any], frame_index: int, fps: int) -> bool:
    blink_override = actor.get("blink") if "blink" in actor else None
    if blink_override is True:
        return True
    if blink_override is False:
        return False
    period = max(12, fps * 3)
    return frame_index % period in (0, 1)


def _apply_layer_stack(character_canvas: Image.Image, bundle: dict[str, Any], actor: dict[str, Any], frame_index: int, fps: int) -> None:
    scale = float(
        actor.get("curr_scale")
        or actor.get("scale")
        or actor.get("target_scale")
        or actor.get("display_scale")
        or 1.0
    )
    base = bundle.get("layers", {}).get("base") or bundle.get("body")
    if base is None:
        return
    target_size = _scale_size(base.size, scale)
    scaled_base = _resize(base, target_size)
    if scaled_base is None:
        return

    layers = bundle.get("layers", {})
    assembly_mode = str(bundle.get("assembly_mode", "legacy")).lower()
    talking = "talk" in str(actor.get("animation_state", "")).lower() or "lip" in str(actor.get("animation_state", "")).lower() or actor.get("is_talking")
    bob = int(round(math.sin((frame_index / max(1.0, fps / 6.0)) + float(actor.get("motion_phase", 0.0))) * (2.0 if talking else 1.0)))
    breathing = 1.0 + (0.005 if talking else 0.003) * math.sin(frame_index / max(1.0, fps / 2.0))
    if breathing != 1.0:
        target_size = _scale_size(target_size, breathing)
        scaled_base = _resize(base, target_size)
        if scaled_base is None:
            return

    _paste(character_canvas, scaled_base, 0, 0)

    face_base = _resize(layers.get("face_base"), target_size)
    if face_base is not None:
        _paste(character_canvas, face_base, 0, 0)

    # Bird feathers / wings first so they sit behind face features.
    feathers = _resize(layers.get("feathers"), target_size)
    if feathers is not None:
        _paste(character_canvas, feathers, 0, 0 + bob)

    wing_left = _resize(layers.get("wing_left"), target_size)
    wing_right = _resize(layers.get("wing_right"), target_size)
    if wing_left is not None or wing_right is not None:
        flap = math.sin((frame_index / max(1.0, fps / 8.0)) + float(actor.get("wing_phase", 0.0)))
        wing_offset = int(round(flap * 4))
        if wing_left is not None:
            x, y = _get_anchor(bundle, actor, "wing_left_anchor_xy")
            _paste(character_canvas, wing_left, x + wing_offset, y + bob)
        if wing_right is not None:
            x, y = _get_anchor(bundle, actor, "wing_right_anchor_xy")
            _paste(character_canvas, wing_right, x - wing_offset, y + bob)

    hair = _resize(layers.get("hair"), target_size)
    if hair is not None:
        x, y = _get_anchor(bundle, actor, "hair_anchor_xy")
        _paste(character_canvas, hair, x, y + bob)

    eyes = layers.get("eyes_blink") if _needs_blink(actor, frame_index, fps) else layers.get("eyes")
    if eyes is not None:
        x, y = _get_anchor(bundle, actor, "eyes_anchor_xy")
        _paste_centered(character_canvas, eyes, x, y + bob)

    mouth_key = actor.get("active_mouth_shape") or _choose_mouth_key(bundle, actor, frame_index, fps)
    mouth = bundle.get("mouths", {}).get(mouth_key) if mouth_key else None
    mouth = _resize(mouth, _scale_size(mouth.size, _mouth_scale(actor, bundle))) if mouth is not None else None
    if mouth is not None:
        x, y = _get_anchor(bundle, actor, "mouth_anchor_xy")
        mouth_bob = bob if assembly_mode == "modular_human" else 0
        _paste_centered(character_canvas, mouth, x, y + mouth_bob)

    accessories = _resize(layers.get("accessories"), target_size)
    if accessories is not None:
        x, y = _get_anchor(bundle, actor, "accessories_anchor_xy")
        _paste(character_canvas, accessories, x, y + bob)


def _place_character(canvas: Image.Image, character_canvas: Image.Image, actor: dict[str, Any]) -> None:
    x, y = actor.get("current_coords", (0, 0))
    x = float(x)
    y = float(y)
    placement_mode = str(
        actor.get("placement_mode")
        or actor.get("position_mode")
        or actor.get("anchor_mode")
        or actor.get("bundle", {}).get("assembly_mode", "legacy")
    ).lower()

    if placement_mode in {"modular_human", "modular_bird"}:
        placement_mode = "ground" if placement_mode == "modular_human" else "center"

    if placement_mode in {"ground", "grounded", "bottom", "bottom_center"}:
        x -= character_canvas.width / 2.0
        y -= character_canvas.height
    elif placement_mode in {"center", "middle", "floating_center"}:
        x -= character_canvas.width / 2.0
        y -= character_canvas.height / 2.0
    # legacy top-left placement falls through unchanged.

    _paste(canvas, character_canvas, x, y)


def compile_cinematic_story_frame(
    frame_index: int,
    fps: int,
    bg_img: Image.Image,
    actors: list,
    manifest_config: dict,
) -> Image.Image:
    """
    Render a frame using modular puppet assets when available, with backward
    compatible fallback to the legacy single-sprite flow.
    """
    canvas_w, canvas_h = tuple(manifest_config.get("canvas_dimensions", bg_img.size))
    frame_canvas = bg_img.convert("RGBA").copy()
    if frame_canvas.size != (canvas_w, canvas_h):
        frame_canvas = frame_canvas.resize((canvas_w, canvas_h), _resample())

    for actor in actors:
        bundle = actor.get("bundle") or {}
        base = bundle.get("layers", {}).get("base") or bundle.get("body")
        if base is None:
            continue

        if bundle.get("assembly_mode") in {"modular_human", "modular_bird"} or any(
            layer_name in bundle.get("layers", {}) for layer_name in ("face_base", "hair", "eyes", "eyes_blink", "wing_left", "wing_right")
        ):
            character_canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
            _apply_layer_stack(character_canvas, bundle, actor, frame_index, fps)
            character_canvas = _apply_body_realism(character_canvas, actor, bundle, frame_index, fps)
            character_canvas = _apply_face_mouth_cover(character_canvas, bundle, actor)
            character_canvas = _apply_ambient_light_match(character_canvas, bg_img, bundle, actor)
            human_arms = _build_human_arm_layer(character_canvas, bundle, actor, frame_index, fps)
            if human_arms is not None:
                character_canvas = Image.alpha_composite(character_canvas, human_arms)
            shadow = _build_character_shadow(character_canvas, actor, bundle, frame_index, fps)
            if shadow is not None:
                shadow_x = max(0, int(round((character_canvas.width - shadow.width) / 2.0)))
                shadow_y = max(0, character_canvas.height - max(8, shadow.height // 2))
                _paste(frame_canvas, shadow, float(actor.get("current_coords", (0, 0))[0]) - shadow.width / 2.0 + shadow_x, float(actor.get("current_coords", (0, 0))[1]) - character_canvas.height + shadow_y)
            _place_character(frame_canvas, character_canvas, actor)
            continue

        # Legacy fallback: draw the original body image at the requested position.
        legacy_canvas = base if base.mode == "RGBA" else base.convert("RGBA")
        legacy_actor = dict(actor)
        legacy_actor.setdefault("placement_mode", "legacy")
        _place_character(frame_canvas, legacy_canvas, legacy_actor)

    return _apply_close_up_crop(frame_canvas, manifest_config, canvas_w, canvas_h)


def render_dynamic_character_frame(
    frame_index: int,
    fps: int,
    character_assets: dict[str, Any],
    active_mouth_shape: str | None = None,
) -> Image.Image:
    """
    Render a character on a transparent canvas for the external 2D compiler.
    """
    bundle = character_assets.get("bundle") if isinstance(character_assets.get("bundle"), dict) else character_assets
    if not isinstance(bundle, dict):
        bundle = character_assets
    base = bundle.get("layers", {}).get("base") or bundle.get("body") or bundle.get("base")
    if base is None:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    actor = dict(character_assets)
    if active_mouth_shape:
        actor["active_mouth_shape"] = active_mouth_shape

    character_canvas = Image.new("RGBA", base.size, (0, 0, 0, 0))
    _apply_layer_stack(character_canvas, bundle, actor, frame_index, fps)
    character_canvas = _apply_body_realism(character_canvas, actor, bundle, frame_index, fps)
    character_canvas = _apply_face_mouth_cover(character_canvas, bundle, actor)
    human_arms = _build_human_arm_layer(character_canvas, bundle, actor, frame_index, fps)
    if human_arms is not None:
        character_canvas = Image.alpha_composite(character_canvas, human_arms)
    return character_canvas


def render_frame(frame_index: int, fps: int, bg_img: Image.Image, actors: list, manifest_config: dict) -> Image.Image:
    return compile_cinematic_story_frame(frame_index, fps, bg_img, actors, manifest_config)


def compose_story_frame(frame_index: int, fps: int, bg_img: Image.Image, actors: list, manifest_config: dict) -> Image.Image:
    return compile_cinematic_story_frame(frame_index, fps, bg_img, actors, manifest_config)


def render_story_frame(frame_index: int, fps: int, bg_img: Image.Image, actors: list, manifest_config: dict) -> Image.Image:
    return compile_cinematic_story_frame(frame_index, fps, bg_img, actors, manifest_config)


render_cinematic_story_frame = compile_cinematic_story_frame
compose_character_frame = compile_cinematic_story_frame
render_actor_frame = compile_cinematic_story_frame
