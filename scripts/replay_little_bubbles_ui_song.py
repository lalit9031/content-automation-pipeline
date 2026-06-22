from __future__ import annotations

import json
import subprocess
from pathlib import Path

from content_pipeline.bots.audio import generate_hindi_song_via_native_audio
from content_pipeline.config import Settings


SOURCE_DIR = Path("/Users/lalitprasadsingh/Desktop/Little_Bubbles_TV_Twinkle_Twinkle_Rich")
IMAGE_PATH = Path("/Users/lalitprasadsingh/Downloads/ChatGPT Image Jun 12, 2026, 01_56_38 PM.png")
DESKTOP_DIR = Path.home() / "Desktop" / "Little_Bubbles_TV_Twinkle_Twinkle_UI_Replay"
PROMPT_PATH = DESKTOP_DIR / "prompt.txt"
LYRICS_PATH = DESKTOP_DIR / "lyrics.txt"
STYLE_PATH = DESKTOP_DIR / "style.txt"
AUDIO_PATH = DESKTOP_DIR / "LittleBubbles_UI_Replay.mp3"
VIDEO_PATH = DESKTOP_DIR / "LittleBubbles_UI_Replay_Shorts.mp4"
MANIFEST_PATH = DESKTOP_DIR / "manifest.json"


def _make_short_video(image_path: Path, audio_path: Path, output_path: Path) -> None:
    width, height = 1080, 1920
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-filter_complex",
            (
                "[0:v]split=2[bgsrc][fgsrc];"
                f"[bgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},boxblur=18:1[bg];"
                "[fgsrc]scale=900:-2:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]"
            ),
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
    )


def main() -> int:
    settings = Settings.from_environment(Path.cwd())
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

    prompt = (SOURCE_DIR / "prompt.txt").read_text(encoding="utf-8").strip()
    lyrics = (SOURCE_DIR / "lyrics.txt").read_text(encoding="utf-8").strip()
    style = (SOURCE_DIR / "style.txt").read_text(encoding="utf-8").strip()

    PROMPT_PATH.write_text(prompt, encoding="utf-8")
    LYRICS_PATH.write_text(lyrics, encoding="utf-8")
    STYLE_PATH.write_text(style, encoding="utf-8")

    generate_hindi_song_via_native_audio(
        lyrics=lyrics,
        output_path=AUDIO_PATH,
        singer_gender="Female",
        selected_ref="None (Text-only)",
        hf_token=settings.hf_token,
        genre="Auto",
        temperature=0.8,
        cfg_coef=1.8,
        style_description=style,
        singer_key="EN_RHYME_ANA_CLEAR",
        mode="Poem/Rhyme",
    )

    _make_short_video(IMAGE_PATH, AUDIO_PATH, VIDEO_PATH)

    manifest = {
        "source_dir": str(SOURCE_DIR),
        "prompt": str(PROMPT_PATH),
        "lyrics": str(LYRICS_PATH),
        "style": str(STYLE_PATH),
        "audio": str(AUDIO_PATH),
        "video": str(VIDEO_PATH),
        "image": str(IMAGE_PATH),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    print(f"Saved final video to: {VIDEO_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
