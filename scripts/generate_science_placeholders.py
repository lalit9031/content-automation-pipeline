"""Generate rich scientific placeholder images for CRISPR documentary scenes.

Uses Pillow to create visually compelling placeholders — dark cinematic
backgrounds with DNA helices, glowing molecules, and text overlays.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")

WIDTH, HEIGHT = 1920, 1080


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _draw_gradient(
    draw: ImageDraw.ImageDraw,
    colors: list[tuple[int, int, int]],
    direction: str = "vertical",
) -> None:
    """Draw a multi-stop gradient."""
    stops = len(colors)
    for y in range(HEIGHT):
        if direction == "vertical":
            t = y / max(HEIGHT - 1, 1)
        else:
            t = 0.5  # fallback
        # Find which stop segment we're in
        seg = t * (stops - 1)
        idx = int(seg)
        frac = seg - idx
        if idx >= stops - 1:
            r, g, b = colors[-1]
        else:
            c1, c2 = colors[idx], colors[idx + 1]
            r = int(c1[0] + (c2[0] - c1[0]) * frac)
            g = int(c1[1] + (c2[1] - c1[1]) * frac)
            b = int(c1[2] + (c2[2] - c1[2]) * frac)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))


def _draw_dna_helix(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    width: int,
    height: int,
    color: tuple[int, int, int],
    alpha: int = 80,
    strands: int = 2,
    wave_count: float = 3.5,
) -> None:
    """Draw a glowing DNA double helix."""
    # Draw sinusoidal backbone strands
    for strand in range(strands):
        phase_offset = math.pi * strand  # 180 deg offset for second strand
        points: list[tuple[float, float]] = []
        for x in range(0, width, 2):
            rel_x = x / width
            angle = rel_x * wave_count * 2 * math.pi + phase_offset
            y_offset = (height * 0.35) * math.sin(angle)
            px = cx - width // 2 + x
            py = cy + y_offset
            points.append((px, py))

        if len(points) > 1:
            for i in range(len(points) - 1):
                draw.line(
                    [points[i], points[i + 1]],
                    fill=(*color, alpha),
                    width=3,
                )

    # Draw rungs (connections between strands)
    for x in range(0, width, 28):
        rel_x = x / width
        angle1 = rel_x * wave_count * 2 * math.pi
        angle2 = rel_x * wave_count * 2 * math.pi + math.pi

        px1 = cx - width // 2 + x
        py1 = cy + (height * 0.35) * math.sin(angle1)
        px2 = cx - width // 2 + x
        py2 = cy + (height * 0.35) * math.sin(angle2)

        # Glow dot at each rung end
        for ppx, ppy in [(px1, py1), (px2, py2)]:
            for r in [4, 2]:
                draw.ellipse(
                    [ppx - r, ppy - r, ppx + r, ppy + r],
                    fill=(*color, alpha + 30 if r == 2 else alpha),
                )


def _draw_molecular_dots(
    draw: ImageDraw.ImageDraw,
    count: int,
    colors: list[tuple[int, int, int]],
    alpha: int = 60,
    min_radius: int = 2,
    max_radius: int = 6,
) -> None:
    """Draw floating molecular/dot particles."""
    random.seed(42)
    for _ in range(count):
        x = random.randint(0, WIDTH)
        y = random.randint(0, HEIGHT)
        r = random.randint(min_radius, max_radius)
        c = random.choice(colors)
        draw.ellipse(
            [x - r, y - r, x + r, y + r],
            fill=(*c, alpha),
        )


def _draw_grid(
    draw: ImageDraw.ImageDraw,
    color: tuple[int, int, int],
    alpha: int = 15,
    spacing: int = 80,
) -> None:
    """Draw a subtle scientific grid."""
    for x in range(0, WIDTH, spacing):
        draw.line([(x, 0), (x, HEIGHT)], fill=(*color, alpha), width=1)
    for y in range(0, HEIGHT, spacing):
        draw.line([(0, y), (WIDTH, y)], fill=(*color, alpha), width=1)


def _draw_glow_circle(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    """Draw a glowing circle with radial falloff."""
    for r in range(radius, 0, -1):
        a = int(120 * (1 - r / radius))
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(*color, a),
        )


def _draw_concentric_rings(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    count: int,
    max_radius: int,
    color: tuple[int, int, int],
    alpha: int = 40,
) -> None:
    """Draw concentric glowing rings (like a petri dish / cell)."""
    for i in range(count):
        r = max_radius * (i + 1) // count
        a = alpha - (i * alpha // count // 2)
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=(*color, max(a, 5)),
            width=2,
        )


def _add_text_overlay(
    draw: ImageDraw.ImageDraw,
    text: str,
    subtitle: str,
) -> None:
    """Add scene title and subtitle text with shadow."""
    try:
        font_title = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/DevanagariMT.ttc", 52
        )
        font_sub = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/DevanagariMT.ttc", 28
        )
    except (IOError, OSError):
        try:
            font_title = ImageFont.truetype(
                "/System/Library/Fonts/Helvetica.ttc", 48
            )
            font_sub = ImageFont.truetype(
                "/System/Library/Fonts/Helvetica.ttc", 26
            )
        except (IOError, OSError):
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

    # Semi-transparent bottom bar
    draw.rectangle(
        [0, HEIGHT - 130, WIDTH, HEIGHT],
        fill=(0, 0, 0, 160),
    )

    # Title shadow + text
    shadow_offset = 2
    for dx, dy, fill_color in [
        (shadow_offset, shadow_offset, (0, 0, 0)),
        (0, 0, (255, 255, 255)),
    ]:
        draw.text(
            (60 + dx, HEIGHT - 115 + dy),
            text,
            fill=(*fill_color, 200),
            font=font_title,
        )

    # Subtitle shadow + text
    for dx, dy, fill_color in [
        (shadow_offset, shadow_offset, (0, 0, 0)),
        (0, 0, (180, 200, 255)),
    ]:
        draw.text(
            (60 + dx, HEIGHT - 75 + dy),
            subtitle,
            fill=(*fill_color, 160),
            font=font_sub,
        )


def _draw_stars(
    draw: ImageDraw.ImageDraw,
    count: int,
    alpha: int = 100,
) -> None:
    """Draw tiny star-like dots for background depth."""
    random.seed(123)
    for _ in range(count):
        x = random.randint(0, WIDTH)
        y = random.randint(0, HEIGHT)
        r = random.choice([1, 1, 1, 2])
        a = random.randint(alpha // 2, alpha)
        draw.ellipse(
            [x - r, y - r, x + r, y + r],
            fill=(200, 220, 255, a),
        )


def generate_placeholder(
    scene_index: int,
    output_path: Path,
    title: str,
    visual_prompt: str,
) -> None:
    """Generate a scientific placeholder image for a CRISPR documentary scene."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # Color palettes based on scene content keywords
    prompt_lower = visual_prompt.lower()
    if "dna" in prompt_lower or "helix" in prompt_lower or "double" in prompt_lower:
        # DNA scenes - deep blue/purple with cyan/teal accents
        gradient_colors = [
            _hex_to_rgb("#050a15"),  # very dark navy
            _hex_to_rgb("#0a1628"),
            _hex_to_rgb("#0f1f3a"),
            _hex_to_rgb("#0a1628"),
        ]
        accent = (0, 200, 255)  # cyan
        accent2 = (120, 80, 220)  # purple
        glow = (0, 150, 255)
        draw_helix = True
        draw_rings = True
    elif "bacterial" in prompt_lower or "chromosome" in prompt_lower:
        # Bacterial scenes - deep teal/green with golden accents
        gradient_colors = [
            _hex_to_rgb("#051510"),
            _hex_to_rgb("#0a2a1a"),
            _hex_to_rgb("#0d3520"),
            _hex_to_rgb("#082818"),
        ]
        accent = (0, 220, 180)  # teal
        accent2 = (255, 200, 50)  # gold
        glow = (0, 180, 150)
        draw_helix = True
        draw_rings = True
    elif "microscope" in prompt_lower or "microscopic" in prompt_lower or "cell" in prompt_lower:
        # Microscopic scenes - deep violet/magenta
        gradient_colors = [
            _hex_to_rgb("#150510"),
            _hex_to_rgb("#280a1a"),
            _hex_to_rgb("#3a0f25"),
            _hex_to_rgb("#280a18"),
        ]
        accent = (255, 100, 200)  # magenta
        accent2 = (100, 200, 255)  # cyan
        glow = (200, 80, 180)
        draw_helix = False
        draw_rings = True
    else:
        # Default - deep cinematic blue
        gradient_colors = [
            _hex_to_rgb("#080c18"),
            _hex_to_rgb("#101830"),
            _hex_to_rgb("#182440"),
            _hex_to_rgb("#101830"),
        ]
        accent = (80, 180, 255)  # light blue
        accent2 = (180, 120, 255)  # lavender
        glow = (60, 140, 255)
        draw_helix = True
        draw_rings = True

    # 1. Background gradient
    _draw_gradient(draw, gradient_colors)

    # 2. Subtle grid
    _draw_grid(draw, (100, 150, 200), alpha=18)

    # 3. Stars / floating particles
    _draw_stars(draw, 300, alpha=80)

    # 4. Molecular dots
    _draw_molecular_dots(
        draw, 150,
        [accent, accent2, (255, 255, 255)],
        alpha=50,
    )

    # 5. DNA helix (for relevant scenes)
    if draw_helix:
        _draw_dna_helix(
            draw,
            cx=WIDTH // 2,
            cy=HEIGHT // 2 - 30,
            width=1600,
            height=400,
            color=accent,
            alpha=70,
        )
        # Second helix slightly offset
        _draw_dna_helix(
            draw,
            cx=WIDTH // 2 + 20,
            cy=HEIGHT // 2 + 10,
            width=1400,
            height=300,
            color=accent2,
            alpha=40,
            wave_count=2.5,
        )

    # 6. Glowing concentric rings (cell/petri dish)
    if draw_rings:
        _draw_concentric_rings(
            draw,
            cx=WIDTH // 2,
            cy=HEIGHT // 2,
            count=8,
            max_radius=450,
            color=glow,
            alpha=30,
        )
        _draw_glow_circle(
            draw,
            cx=WIDTH // 4,
            cy=HEIGHT // 3,
            radius=60,
            color=accent,
        )
        _draw_glow_circle(
            draw,
            cx=3 * WIDTH // 4,
            cy=2 * HEIGHT // 3,
            radius=40,
            color=accent2,
        )

    # 7. Scene label text overlay
    short_prompt = visual_prompt.split(".")[0].strip()[:80]
    _add_text_overlay(draw, title, short_prompt)

    # Save as RGB PNG
    img_rgb = img.convert("RGB")
    img_rgb.save(str(output_path), "PNG", optimize=True)
    print(f"  Created: {output_path.name} ({output_path.stat().st_size} bytes)")


def main() -> None:
    import sys
    if len(sys.argv) < 2:
        print("Usage: python generate_science_placeholders.py <workspace_dir>")
        sys.exit(1)

    ws = Path(sys.argv[1])
    script = json.loads((ws / "script.json").read_text("utf-8"))
    img_dir = ws / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    scenes_to_replace = [1, 2, 11, 12]

    for scene_num in scenes_to_replace:
        scene = script["scenes"][scene_num - 1]
        title = scene["title"]
        visual_prompt = scene.get("visual_prompt", "")
        output = img_dir / f"scene_{scene_num:04d}.png"

        print(f"\n--- Scene {scene_num}: {title} ---")
        generate_placeholder(scene_num, output, title, visual_prompt)

    print("\nDone! 4 placeholder images generated.")


if __name__ == "__main__":
    main()
