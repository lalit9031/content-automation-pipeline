"""
rigging_engine.py — Procedural joint-pivot rigging for 3/4 view modular puppets.

Layer compositing order (back -> front):
  1. far_arm   -- rotates around far_shoulder_xy (sits BEHIND torso)
  2. torso     -- rigid body / clothes mesh
  3. head      -- head plate with face, hair, eyes, blink
  4. mouth     -- Rhubarb lip-sync frame, center-anchored on mouth_anchor_xy
  5. near_arm  -- rotates around near_shoulder_xy (sits IN FRONT of torso)

Gesture states accepted:
  idle, talk/talking_lip_sync, wave, point, walk, pranaam

Ambient lighting: pass ambient_tint=(R,G,B,alpha) in actor dict to tint
  the puppet to match scene lighting (night=dark-blue, sunset=warm-orange).
"""
from __future__ import annotations

import math
from typing import Any

from PIL import Image, ImageDraw, ImageFilter


def _resample() -> int:
    return getattr(Image, "Resampling", Image).LANCZOS


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def apply_ambient_tint(puppet: Image.Image, tint_rgba: tuple) -> Image.Image:
    """
    Overlay a semi-transparent solid colour on the puppet to simulate
    scene ambient lighting (e.g. blue for night, orange for sunset).
    tint_rgba = (R, G, B, alpha)  where alpha 0-255 (0=no tint, 80=subtle).
    """
    if tint_rgba is None or tint_rgba[3] == 0:
        return puppet
    r, g, b, a = tint_rgba
    tint_layer = Image.new("RGBA", puppet.size, (r, g, b, 0))
    # Apply tint only where puppet has visible pixels
    puppet_alpha = puppet.getchannel("A")
    # Scale tint alpha by puppet alpha using a fast lookup table
    lut = [int(x * a / 255.0) for x in range(256)]
    tint_a = puppet_alpha.point(lut)
    tint_layer.putalpha(tint_a)
    result = puppet.copy()
    result.alpha_composite(tint_layer)
    return result



def draw_foot_shadow(canvas: Image.Image, cx: int, feet_y: int,
                     width: int = 80, opacity: int = 60) -> None:
    """
    Draw a soft elliptical drop-shadow under character feet.
    Call on the SCENE canvas (not puppet) BEFORE pasting the puppet.
    """
    draw = ImageDraw.Draw(canvas, "RGBA")
    hw = width // 2
    hh = max(6, width // 8)
    box = [cx - hw, feet_y - hh, cx + hw, feet_y + hh]
    # Draw 3 progressively lighter ellipses for soft falloff
    for i in range(3, 0, -1):
        exp = i * 6
        alpha = opacity // i
        draw.ellipse(
            [box[0]-exp, box[1]-exp//3, box[2]+exp, box[3]+exp//3],
            fill=(0, 0, 0, alpha)
        )


def _paste(canvas: Image.Image, layer: Image.Image | None, x: float, y: float) -> None:
    if layer is None:
        return
    if layer.mode != "RGBA":
        layer = layer.convert("RGBA")
    canvas.paste(layer, (int(round(x)), int(round(y))), layer)


def _paste_centered(
    canvas: Image.Image,
    layer: Image.Image | None,
    anchor_x: float,
    anchor_y: float,
) -> None:
    """Paste layer so its opaque-content centre lands on anchor."""
    if layer is None:
        return
    if layer.mode != "RGBA":
        layer = layer.convert("RGBA")
    alpha = layer.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return
    crop = layer.crop(bbox)
    cx = bbox[0] + crop.width / 2.0
    cy = bbox[1] + crop.height / 2.0
    canvas.paste(crop, (int(round(anchor_x - cx)), int(round(anchor_y - cy))), crop)


def _rotate_around_pivot(
    layer: Image.Image,
    angle_deg: float,
    pivot_x: float,
    pivot_y: float,
    canvas_size: tuple[int, int],
) -> Image.Image:
    """
    Rotate `layer` (same size as canvas) around the given pixel pivot.
    Returns a new image of `canvas_size` with the rotated layer composited
    on a transparent background.
    """
    if abs(angle_deg) < 0.05:
        return layer

    # Rotate directly around pivot using PIL's center argument
    if layer.mode != "RGBA":
        layer = layer.convert("RGBA")
    return layer.rotate(
        -angle_deg,  # PIL is counter-clockwise positive
        resample=Image.Resampling.BICUBIC,
        center=(pivot_x, pivot_y),
        expand=False,
    )



def _needs_blink(actor: dict[str, Any], frame_index: int, fps: int) -> bool:
    override = actor.get("blink")
    if override is True:
        return True
    if override is False:
        return False
    # Blink every ~5 seconds, lasting 2 frames
    period = max(20, fps * 5)
    return frame_index % period in (0, 1)


def _choose_mouth_key(
    bundle: dict[str, Any], actor: dict[str, Any], frame_index: int, fps: int
) -> str | None:
    mouths = bundle.get("mouths") or {}
    if not mouths:
        return None

    # Explicit override from actor (e.g. active_mouth_shape set by scene_compiler)
    direct = (
        actor.get("active_mouth_shape")
        or actor.get("mouth_state")
        or actor.get("mouth_key")
        or actor.get("phoneme")
    )
    if isinstance(direct, str) and direct.strip().upper() in mouths:
        return direct.strip().upper()

    animation_state = str(actor.get("animation_state", "")).lower()
    talking = (
        "talk" in animation_state
        or "lip" in animation_state
        or actor.get("is_talking")
    )

    # When NOT talking, always return the neutral/closed mouth shape
    if not talking:
        for neutral_key in ("X", "A"):
            if neutral_key in mouths:
                return neutral_key
        # No X or A — return first available
        return sorted(mouths.keys())[0] if mouths else None

    # When talking, cycle through animated mouth shapes
    ordered = [k for k in ("A", "B", "C", "D", "E", "F", "G", "H") if k in mouths]
    if not ordered:
        ordered = [k for k in sorted(mouths.keys()) if k != "X"]
    if not ordered:
        ordered = sorted(mouths.keys())
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]

    tick = max(1, fps // 8)
    return ordered[(frame_index // tick) % len(ordered)]


def _get_joint(bundle: dict[str, Any], key: str) -> tuple[float, float]:
    """Read a joint coordinate, checking both metadata.joints and flat bundle anchors."""
    meta = bundle.get("metadata", {}) or {}
    joints = meta.get("joints") or bundle.get("joints") or {}
    if key in joints:
        v = joints[key]
        return float(v[0]), float(v[1])
    # Fallback: look in anchors
    anchors = bundle.get("anchors") or {}
    if key in anchors:
        v = anchors[key]
        return float(v[0]), float(v[1])
    return 0.0, 0.0


def _get_gesture_limits(bundle: dict[str, Any]) -> dict[str, Any]:
    meta = bundle.get("metadata", {}) or {}
    defaults = {
        "idle_sway_bounds": [-3.0, 3.0],
        "point_angle": -65.0,
        "wave_angle_bounds": [15.0, 55.0],
        "pranaam_near_angle": 55.0,   # near arm bows forward
        "pranaam_far_angle":  45.0,   # far arm matches
    }
    limits = meta.get("gesture_limits") or bundle.get("gesture_limits") or {}
    return {**defaults, **limits}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def render_articulated_puppet(
    frame_index: int,
    fps: int,
    bundle: dict[str, Any],
    gesture_state: str = "idle",
    actor: dict[str, Any] | None = None,
) -> Image.Image:
    """
    Assemble a 3/4-view puppet with pivot-based arm rotation.

    Returns an RGBA Image on a transparent canvas the same size as the torso layer.
    """
    if actor is None:
        actor = {}

    layers = bundle.get("layers", {})
    torso = layers.get("torso") or layers.get("base") or bundle.get("body")
    if torso is None:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    canvas_size = torso.size
    cw, ch = canvas_size
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))

    t = frame_index / max(1, fps)
    phase = float(actor.get("motion_phase", 0.0))
    idle_osc = math.sin(2.0 * math.pi * t / 1.8 + phase)
    breathe = 1.0 + 0.006 * math.sin(2.0 * math.pi * t / 0.55 + phase)
    talking = (
        "talk" in str(gesture_state).lower()
        or "lip" in str(gesture_state).lower()
        or actor.get("is_talking")
    )

    limits = _get_gesture_limits(bundle)
    far_shoulder_x, far_shoulder_y = _get_joint(bundle, "far_shoulder_xy")
    near_shoulder_x, near_shoulder_y = _get_joint(bundle, "near_shoulder_xy")

    # ── Arm angle calculation ─────────────────────────────────────────────────
    gs = str(gesture_state).lower()

    # Far arm (behind torso)
    far_sway = limits["idle_sway_bounds"][0] * idle_osc * (2.0 if talking else 1.2)
    if "walk" in gs:
        far_sway = 22.0 * math.sin(2.0 * math.pi * t * 1.5 + phase)
    elif "pranaam" in gs:
        # Both arms come together forward for pranam bow
        far_sway = float(limits["pranaam_far_angle"])

    # Near arm (in front of torso)
    if "point" in gs:
        near_angle = float(limits["point_angle"])
    elif "wave" in gs:
        wb = limits["wave_angle_bounds"]
        mid = (wb[0] + wb[1]) / 2.0
        amp = (wb[1] - wb[0]) / 2.0
        near_angle = mid + amp * math.sin(2.0 * math.pi * 4.0 * t)
    elif "walk" in gs:
        near_angle = -22.0 * math.sin(2.0 * math.pi * t * 1.5 + phase)
    elif "pranaam" in gs:
        near_angle = float(limits["pranaam_near_angle"])
    elif talking:
        near_angle = limits["idle_sway_bounds"][1] * idle_osc * 2.2
    else:
        near_angle = limits["idle_sway_bounds"][1] * idle_osc * 1.2

    # ── Compositing (back → front) ────────────────────────────────────────────

    # 1. Far arm (behind torso)
    far_arm_img = layers.get("far_arm")
    if far_arm_img is not None:
        rotated_far = _rotate_around_pivot(
            far_arm_img, far_sway, far_shoulder_x, far_shoulder_y, canvas_size
        )
        canvas.alpha_composite(rotated_far)

    # 2. Torso (rigid body + clothes)
    torso_layer = layers.get("torso") or layers.get("base") or bundle.get("body")
    if torso_layer is not None:
        if breathe != 1.0:
            tw = max(1, int(round(cw * breathe)))
            th = max(1, int(round(ch * breathe)))
            torso_scaled = torso_layer.resize((tw, th), _resample())
            # Re-centre
            tmp = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
            tmp.paste(torso_scaled, ((cw - tw) // 2, (ch - th) // 2), torso_scaled)
            canvas.alpha_composite(tmp)
        else:
            canvas.alpha_composite(torso_layer)

    # 3. Head plate (face_base + hair on full-canvas layer)
    head_plate = layers.get("head") or layers.get("face_base")
    if head_plate is not None:
        canvas.alpha_composite(head_plate)
    else:
        # Fall back to face_base as a full-canvas layer
        fb = layers.get("face_base")
        if fb is not None:
            canvas.alpha_composite(fb)

    # 4. Hair (on top of head plate)
    hair = layers.get("hair")
    if hair is not None:
        bob = int(round(math.sin(frame_index / max(1.0, fps / 6.0) + phase) * (1.5 if talking else 0.8)))
        anchors = bundle.get("anchors") or {}
        hx = float((anchors.get("hair_anchor_xy") or [0, 0])[0])
        hy = float((anchors.get("hair_anchor_xy") or [0, 0])[1])
        _paste(canvas, hair, hx, hy + bob)

    # 5. Eyes / blink
    bob = int(round(math.sin(frame_index / max(1.0, fps / 6.0) + phase) * (1.5 if talking else 0.8)))
    eyes_layer = layers.get("eyes_blink") if _needs_blink(actor, frame_index, fps) else layers.get("eyes")
    if eyes_layer is not None:
        anchors = bundle.get("anchors") or {}
        ex = float((anchors.get("eyes_anchor_xy") or [cw / 2, ch * 0.2])[0])
        ey = float((anchors.get("eyes_anchor_xy") or [cw / 2, ch * 0.2])[1])
        _paste_centered(canvas, eyes_layer, ex, ey + bob)

    # 6. Mouth (Rhubarb lip-sync)
    mouth_key = _choose_mouth_key(bundle, actor | {"animation_state": gesture_state}, frame_index, fps)
    mouth_img = bundle.get("mouths", {}).get(mouth_key) if mouth_key else None
    if mouth_img is not None:
        anchors = bundle.get("anchors") or {}
        mx = float((anchors.get("mouth_anchor_xy") or [cw / 2, ch * 0.28])[0])
        my = float((anchors.get("mouth_anchor_xy") or [cw / 2, ch * 0.28])[1])
        scale = float(actor.get("curr_scale") or actor.get("scale") or 1.0)
        # Mouth sprites are 200x200 — scale to about 75% for proper face proportion
        mouth_scale = _clamp(scale * 0.75, 0.55, 1.30)
        mw = max(1, int(round(mouth_img.width * mouth_scale)))
        mh = max(1, int(round(mouth_img.height * mouth_scale)))
        mouth_scaled = mouth_img.resize((mw, mh), _resample())
        _paste_centered(canvas, mouth_scaled, mx, my + bob)

    # 7. Near arm (in front of torso + head)
    near_arm_img = layers.get("near_arm")
    if near_arm_img is not None:
        rotated_near = _rotate_around_pivot(
            near_arm_img, near_angle, near_shoulder_x, near_shoulder_y, canvas_size
        )
        canvas.alpha_composite(rotated_near)

    # 8. Accessories (hat, prop, etc.)
    accessories = layers.get("accessories")
    if accessories is not None:
        canvas.alpha_composite(accessories)

    # 9. Ambient lighting tint — must come LAST so it covers all layers uniformly
    #    Pass ambient_tint=(R, G, B, alpha) in actor dict or bundle metadata.
    #    Presets: night=(20,40,80,65)  sunset=(255,140,60,45)  morning=(255,220,160,30)
    tint = actor.get("ambient_tint") or bundle.get("ambient_tint")
    if tint:
        canvas = apply_ambient_tint(canvas, tuple(tint))

    return canvas


def has_joint_rig(bundle: dict[str, Any]) -> bool:
    """Return True if this bundle has enough data for the rigging engine."""
    meta = bundle.get("metadata", {}) or {}
    joints = meta.get("joints") or bundle.get("joints") or {}
    layers = bundle.get("layers", {})
    # Need at least torso or base, plus at least one arm layer
    has_body = "torso" in layers or "base" in layers or bundle.get("body") is not None
    has_arms = "near_arm" in layers or "far_arm" in layers
    return has_body and (bool(joints) or has_arms)
