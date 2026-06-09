import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

def draw_grid_on_image(img_path: Path, output_path: Path, step: int = 20):
    img = Image.open(img_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    # Draw horizontal and vertical grid lines
    for x in range(0, w, step):
        draw.line([x, 0, x, h], fill=(255, 0, 0, 100), width=1)
        if x % 100 == 0:
            draw.text((x + 2, 5), str(x), fill=(255, 0, 0, 255))
            
    for y in range(0, h, step):
        draw.line([0, y, w, y], fill=(255, 0, 0, 100), width=1)
        if y % 100 == 0:
            draw.text((5, y + 2), str(y), fill=(255, 0, 0, 255))
            
    img.save(output_path, "PNG")
    print(f"Saved grid image to {output_path}")

def main():
    assets_dir = Path("/Users/lalitprasadsingh/.gemini/antigravity/scratch/KidsStudio-Orchestrator/assets/character")
    brain_dir = Path("/Users/lalitprasadsingh/.gemini/antigravity/brain/de8cee56-ef36-4fbe-bd0e-a324495c02a6")
    
    kalu_cropped = assets_dir / "kalu_body.png"
    nandu_cropped = assets_dir / "nandu_body.png"
    
    # Resize Kalu to 250 width (aspect ratio kept: 760x742 -> 250x244)
    kalu_resized = Image.open(kalu_cropped)
    k_w, k_h = kalu_resized.size
    kalu_scaled_w = 250
    kalu_scaled_h = int(k_h * (kalu_scaled_w / k_w))
    kalu_resized = kalu_resized.resize((kalu_scaled_w, kalu_scaled_h), Image.Resampling.LANCZOS)
    kalu_temp_path = assets_dir / "kalu_resized.png"
    kalu_resized.save(kalu_temp_path, "PNG")
    
    # Resize Nandu to 160 width (aspect ratio kept: 327x911 -> 160x446)
    nandu_resized = Image.open(nandu_cropped)
    n_w, n_h = nandu_resized.size
    nandu_scaled_w = 160
    nandu_scaled_h = int(n_h * (nandu_scaled_w / n_w))
    nandu_resized = nandu_resized.resize((nandu_scaled_w, nandu_scaled_h), Image.Resampling.LANCZOS)
    nandu_temp_path = assets_dir / "nandu_resized.png"
    nandu_resized.save(nandu_temp_path, "PNG")
    
    # Draw grids to inspect
    draw_grid_on_image(kalu_temp_path, brain_dir / "kalu_grid.png", step=20)
    draw_grid_on_image(nandu_temp_path, brain_dir / "nandu_grid.png", step=20)

if __name__ == "__main__":
    main()
