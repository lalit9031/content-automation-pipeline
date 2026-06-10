from __future__ import annotations

import asyncio
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont
from pydub import AudioSegment
from pydub.generators import Sine


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "hindi_alphabet_direct_video"
FRAME_DIR = OUT_DIR / "frames"
AUDIO_DIR = OUT_DIR / "audio"
WIDTH = 1280
HEIGHT = 720
FPS = 24


@dataclass(frozen=True)
class Slide:
    title: str
    spoken: str
    display_lines: tuple[str, ...]
    letters: tuple[tuple[str, str, str], ...]
    duration: float
    palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]


SLIDES: list[Slide] = [
    Slide(
        title="Hindi Akshar Pyaare",
        spoken="आओ बच्चों सीखें हम, हिंदी अक्षर प्यारे। बोलो, गाओ, याद करो, मज़ेदार ये सारे।",
        display_lines=("आओ बच्चों सीखें हम", "हिंदी अक्षर प्यारे", "बोलो, गाओ, याद करो"),
        letters=(),
        duration=8.0,
        palette=((44, 186, 255), (255, 229, 89), (255, 84, 156)),
    ),
    Slide(
        title="Part 1",
        spoken=(
            "क, क से कबूतर। ख, ख से खरगोश। ग, ग से गमला। घ, घ से घर। ङ, ङ से अंगूर। "
            "रीपीट बच्चों, रीपीट बच्चों। क ख ग घ ङ। हिंदी अक्षर सीखना है, कितना प्यारा, कितना अच्छा।"
        ),
        display_lines=("क से कबूतर", "ख से खरगोश", "ग से गमला", "घ से घर", "ङ से अंगूर"),
        letters=(("क", "कबूतर", "bird"), ("ख", "खरगोश", "rabbit"), ("ग", "गमला", "pot"), ("घ", "घर", "home"), ("ङ", "अंगूर", "grapes")),
        duration=19.0,
        palette=((86, 205, 255), (95, 230, 168), (255, 216, 77)),
    ),
    Slide(
        title="Part 2",
        spoken=(
            "च, च से चम्मच। छ, छ से छाता। ज, ज से जहाज़। झ, झ से झंडा। ञ, ञ से ज्ञान। "
            "रीपीट बच्चों, रीपीट बच्चों। च छ ज झ ञ। हिंदी अक्षर सीखना है, कितना प्यारा, कितना अच्छा।"
        ),
        display_lines=("च से चम्मच", "छ से छाता", "ज से जहाज़", "झ से झंडा", "ञ से ज्ञान"),
        letters=(("च", "चम्मच", "spoon"), ("छ", "छाता", "umbrella"), ("ज", "जहाज़", "ship"), ("झ", "झंडा", "flag"), ("ञ", "ज्ञान", "book")),
        duration=19.0,
        palette=((80, 225, 225), (255, 159, 64), (170, 107, 255)),
    ),
    Slide(
        title="Part 3",
        spoken=(
            "ट, ट से टमाटर। ठ, ठ से ठेला। ड, ड से डमरू। ढ, ढ से ढोल। ण, ण से बाण। "
            "रीपीट बच्चों, रीपीट बच्चों। ट ठ ड ढ ण। हिंदी अक्षर सीखना है, कितना प्यारा, कितना अच्छा।"
        ),
        display_lines=("ट से टमाटर", "ठ से ठेला", "ड से डमरू", "ढ से ढोल", "ण से बाण"),
        letters=(("ट", "टमाटर", "tomato"), ("ठ", "ठेला", "cart"), ("ड", "डमरू", "drum"), ("ढ", "ढोल", "dhol"), ("ण", "बाण", "arrow")),
        duration=19.0,
        palette=((255, 91, 91), (255, 210, 82), (92, 200, 255)),
    ),
    Slide(
        title="Part 4",
        spoken=(
            "त, त से तरबूज। थ, थ से थाली। द, द से दरवाज़ा। ध, ध से धनुष। न, न से नाव। "
            "रीपीट बच्चों, रीपीट बच्चों। त थ द ध न। हिंदी अक्षर सीखना है, कितना प्यारा, कितना अच्छा।"
        ),
        display_lines=("त से तरबूज", "थ से थाली", "द से दरवाज़ा", "ध से धनुष", "न से नाव"),
        letters=(("त", "तरबूज", "watermelon"), ("थ", "थाली", "plate"), ("द", "दरवाज़ा", "door"), ("ध", "धनुष", "bow"), ("न", "नाव", "boat")),
        duration=19.0,
        palette=((255, 71, 145), (67, 203, 255), (255, 226, 89)),
    ),
    Slide(
        title="Part 5",
        spoken=(
            "प, प से पतंग। फ, फ से फल। ब, ब से बकरी। भ, भ से भालू। म, म से मछली। "
            "रीपीट बच्चों, रीपीट बच्चों। प फ ब भ म। हिंदी अक्षर सीखना है, कितना प्यारा, कितना अच्छा।"
        ),
        display_lines=("प से पतंग", "फ से फल", "ब से बकरी", "भ से भालू", "म से मछली"),
        letters=(("प", "पतंग", "kite"), ("फ", "फल", "fruit"), ("ब", "बकरी", "goat"), ("भ", "भालू", "bear"), ("म", "मछली", "fish")),
        duration=19.0,
        palette=((104, 217, 255), (255, 143, 74), (92, 227, 124)),
    ),
    Slide(
        title="Final Chorus",
        spoken=(
            "क ख ग घ ङ। च छ ज झ ञ। ट ठ ड ढ ण। त थ द ध न। प फ ब भ म। "
            "हमने सीखे हिंदी अक्षर, सब बच्चों ने याद किये। गाओ, बोलो, मुस्कुराओ, फिर से सब दोहराओ।"
        ),
        display_lines=("क ख ग घ ङ", "च छ ज झ ञ", "ट ठ ड ढ ण", "त थ द ध न", "प फ ब भ म"),
        letters=(),
        duration=16.0,
        palette=((84, 140, 255), (255, 96, 157), (255, 230, 76)),
    ),
    Slide(
        title="Outro",
        spoken=(
            "क से कबूतर। ख से खरगोश। ग से गमला। घ से घर। "
            "हिंदी अक्षर प्यारे हैं, सीखना सबको अच्छा है।"
        ),
        display_lines=("क से कबूतर", "ख से खरगोश", "ग से गमला", "घ से घर", "हिंदी अक्षर प्यारे हैं"),
        letters=(),
        duration=11.0,
        palette=((52, 211, 153), (96, 165, 250), (251, 191, 36)),
    ),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/NotoSansDevanagari-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def rounded_box(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: tuple[int, int, int], outline=(255, 255, 255), width=4) -> None:
    draw.rounded_rectangle(xy, radius=28, fill=fill, outline=outline, width=width)


def draw_bg(draw: ImageDraw.ImageDraw, slide: Slide, progress: float) -> None:
    c1, c2, c3 = slide.palette
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        mix = tuple(int(c1[i] * (1 - ratio) + c2[i] * ratio) for i in range(3))
        draw.line((0, y, WIDTH, y), fill=mix)
    for i in range(18):
        x = int((i * 173 + progress * 90) % (WIDTH + 180)) - 90
        y = int(40 + (i * 97) % 610)
        r = 18 + (i % 5) * 9
        color = (*c3, 65)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)


def draw_icon(draw: ImageDraw.ImageDraw, kind: str, cx: int, cy: int, scale: float) -> None:
    s = int(52 * scale)
    if kind in {"bird", "rabbit", "goat", "bear"}:
        body = {"bird": (82, 190, 106), "rabbit": (245, 245, 245), "goat": (235, 235, 220), "bear": (142, 92, 58)}[kind]
        draw.ellipse((cx - s, cy - s, cx + s, cy + s), fill=body, outline=(55, 55, 55), width=3)
        draw.ellipse((cx - s // 3, cy - s // 5, cx - s // 8, cy), fill=(30, 30, 30))
        draw.ellipse((cx + s // 8, cy - s // 5, cx + s // 3, cy), fill=(30, 30, 30))
        if kind == "bird":
            draw.polygon((cx + s, cy, cx + s + 34, cy - 16, cx + s + 34, cy + 16), fill=(255, 105, 75))
        if kind == "rabbit":
            draw.ellipse((cx - s // 2, cy - s * 2, cx - s // 7, cy - s // 2), fill=body, outline=(55, 55, 55), width=3)
            draw.ellipse((cx + s // 7, cy - s * 2, cx + s // 2, cy - s // 2), fill=body, outline=(55, 55, 55), width=3)
    elif kind in {"pot", "home", "door", "plate", "cart"}:
        fill = {"pot": (166, 105, 58), "home": (255, 221, 130), "door": (177, 94, 43), "plate": (235, 245, 255), "cart": (173, 113, 57)}[kind]
        draw.rounded_rectangle((cx - s, cy - s, cx + s, cy + s), radius=18, fill=fill, outline=(70, 60, 45), width=4)
        if kind == "home":
            draw.polygon((cx - s - 15, cy - s, cx, cy - s - 65, cx + s + 15, cy - s), fill=(231, 76, 60), outline=(70, 60, 45))
    elif kind in {"grapes", "tomato", "watermelon", "fruit"}:
        colors = {"grapes": (126, 87, 194), "tomato": (231, 76, 60), "watermelon": (46, 204, 113), "fruit": (255, 159, 67)}
        color = colors[kind]
        for dx, dy in [(-24, -14), (0, -18), (24, -14), (-12, 12), (12, 12), (0, 38)]:
            draw.ellipse((cx + dx - 20, cy + dy - 20, cx + dx + 20, cy + dy + 20), fill=color, outline=(50, 80, 40), width=3)
    elif kind in {"spoon", "umbrella", "ship", "flag", "book", "drum", "dhol", "arrow", "bow", "boat", "kite", "fish"}:
        color = (255, 255, 255)
        accent = (255, 84, 156)
        if kind == "umbrella":
            draw.pieslice((cx - s, cy - s, cx + s, cy + s), 180, 360, fill=accent, outline=color, width=4)
            draw.line((cx, cy, cx, cy + s), fill=color, width=5)
        elif kind == "kite":
            draw.polygon((cx, cy - s, cx + s, cy, cx, cy + s, cx - s, cy), fill=accent, outline=color)
            draw.line((cx, cy + s, cx + 40, cy + s + 60), fill=color, width=3)
        elif kind == "fish":
            draw.ellipse((cx - s, cy - s // 2, cx + s, cy + s // 2), fill=(75, 192, 255), outline=color, width=4)
            draw.polygon((cx + s, cy, cx + s + 45, cy - 35, cx + s + 45, cy + 35), fill=(75, 192, 255), outline=color)
        else:
            draw.rounded_rectangle((cx - s, cy - 36, cx + s, cy + 36), radius=18, fill=accent, outline=color, width=4)


def draw_slide(slide: Slide, progress: float) -> Image.Image:
    img = Image.new("RGBA", (WIDTH, HEIGHT), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    draw_bg(draw, slide, progress)

    title_font = font(56, bold=True)
    line_font = font(39, bold=True)
    letter_font = font(88, bold=True)
    word_font = font(30, bold=True)

    draw.rounded_rectangle((34, 28, 1246, 104), radius=30, fill=(255, 255, 255, 220))
    draw.text((64, 43), slide.title, fill=(32, 42, 68), font=title_font)

    if slide.letters:
        cols = len(slide.letters)
        card_w = 220
        gap = 22
        start_x = (WIDTH - (cols * card_w + (cols - 1) * gap)) // 2
        for idx, (letter, word, kind) in enumerate(slide.letters):
            x = start_x + idx * (card_w + gap)
            pulse = 1.0 + 0.035 * math.sin(progress * math.tau + idx)
            rounded_box(draw, (x, 148, x + card_w, 610), fill=(255, 255, 255), outline=(255, 255, 255))
            draw.text((x + 72, 166), letter, fill=(24, 81, 168), font=letter_font)
            draw_icon(draw, kind, x + card_w // 2, 360, pulse)
            tw = draw.textbbox((0, 0), word, font=word_font)
            draw.text((x + (card_w - (tw[2] - tw[0])) // 2, 526), word, fill=(33, 43, 62), font=word_font)
    else:
        y = 165
        for idx, line in enumerate(slide.display_lines):
            fill = (255, 255, 255, 230) if idx % 2 == 0 else (255, 245, 174, 235)
            draw.rounded_rectangle((180, y - 8, 1100, y + 70), radius=26, fill=fill)
            bbox = draw.textbbox((0, 0), line, font=line_font)
            draw.text(((WIDTH - (bbox[2] - bbox[0])) // 2, y), line, fill=(24, 49, 95), font=line_font)
            y += 92

    draw.rounded_rectangle((250, 638, 1030, 694), radius=25, fill=(0, 0, 0, 90))
    draw.text((310, 646), "Bolo, gaao, repeat karo!", fill=(255, 255, 255), font=font(32, bold=True))
    return img.convert("RGB")


async def synthesize_voice() -> Path:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    full_text = " ".join(slide.spoken for slide in SLIDES)
    out = AUDIO_DIR / "hindi_alphabet_voice.mp3"
    communicate = edge_tts.Communicate(full_text, voice="hi-IN-SwaraNeural", rate="-6%", pitch="+3Hz")
    await communicate.save(str(out))
    return out


def create_music_bed(duration_ms: int) -> AudioSegment:
    beat = AudioSegment.silent(duration=duration_ms)
    for i, freq in enumerate((261.63, 329.63, 392.0, 523.25)):
        tone = Sine(freq).to_audio_segment(duration=280).apply_gain(-23)
        for t in range(i * 220, duration_ms, 1400):
            beat = beat.overlay(tone.fade_in(20).fade_out(80), position=t)
    clap = Sine(880).to_audio_segment(duration=65).apply_gain(-30).fade_out(50)
    for t in range(700, duration_ms, 1400):
        beat = beat.overlay(clap, position=t)
    return beat


def build_video(voice_path: Path) -> Path:
    FRAME_DIR.mkdir(parents=True, exist_ok=True)
    voice = AudioSegment.from_file(voice_path)
    target_ms = max(int(sum(slide.duration for slide in SLIDES) * 1000), len(voice) + 1200)
    music = create_music_bed(target_ms)
    mixed = music.overlay(voice.apply_gain(1.5), position=400).fade_out(1200)
    mixed_path = AUDIO_DIR / "hindi_alphabet_mixed.mp3"
    mixed.export(mixed_path, format="mp3", bitrate="192k")

    total_duration = len(mixed) / 1000.0
    total_frames = int(math.ceil(total_duration * FPS))
    slide_times = []
    cursor = 0.0
    total_declared = sum(slide.duration for slide in SLIDES)
    scale = total_duration / total_declared
    for slide in SLIDES:
        dur = slide.duration * scale
        slide_times.append((cursor, cursor + dur, slide))
        cursor += dur

    for frame_idx in range(total_frames):
        t = frame_idx / FPS
        current = slide_times[-1][2]
        start = slide_times[-1][0]
        end = slide_times[-1][1]
        for s, e, slide in slide_times:
            if s <= t < e:
                current = slide
                start = s
                end = e
                break
        progress = (t - start) / max(0.001, end - start)
        frame = draw_slide(current, progress)
        frame.save(FRAME_DIR / f"frame_{frame_idx:05d}.png", quality=92)

    output = OUT_DIR / "hindi_alphabet_direct_video.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        str(FRAME_DIR / "frame_%05d.png"),
        "-i",
        str(mixed_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output),
    ]
    subprocess.run(cmd, check=True)
    return output


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    voice_path = asyncio.run(synthesize_voice())
    output = build_video(voice_path)
    print(output)


if __name__ == "__main__":
    main()
