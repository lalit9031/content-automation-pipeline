from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

PROJECT_ROOT = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/KidsStudio-Orchestrator")
char_dir = PROJECT_ROOT / "assets" / "character"

def draw_grid_on_image(img_path: Path, output_path: Path):
    img = Image.open(img_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    # Try to load a font
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
        
    # Draw horizontal lines and labels
    for y in range(0, h, 50):
        draw.line([0, y, w, y], fill=(255, 0, 0, 100), width=1)
        draw.text((5, y + 2), f"y={y}", fill=(255, 0, 0, 255), font=font)
        
    # Draw vertical lines and labels
    for x in range(0, w, 50):
        draw.line([x, 0, x, h], fill=(0, 0, 255, 100), width=1)
        draw.text((x + 2, 5), f"x={x}", fill=(0, 0, 255, 255), font=font)
        
    img.save(output_path, "PNG")
    print(f"Saved grid image to: {output_path}")

def main():
    draw_grid_on_image(char_dir / "peacock_body.png", PROJECT_ROOT / "output" / "peacock_grid.png")
    draw_grid_on_image(char_dir / "kalu_body.png", PROJECT_ROOT / "output" / "kalu_grid.png")

if __name__ == "__main__":
    main()
