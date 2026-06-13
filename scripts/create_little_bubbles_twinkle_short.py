from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import requests
from PIL import Image

from content_pipeline.bots.audio import generate_hindi_song_via_native_audio
from content_pipeline.bots.singer_manifest import SINGER_ALIASES, SINGER_MANIFEST
from content_pipeline.config import Settings


IMAGE_PATH = Path("/Users/lalitprasadsingh/Downloads/ChatGPT Image Jun 12, 2026, 01_56_38 PM.png")
DESKTOP_DIR = Path.home() / "Desktop" / "Little_Bubbles_TV_Twinkle_Twinkle_Rich"
PROMPT_PATH = DESKTOP_DIR / "prompt.txt"
LYRICS_PATH = DESKTOP_DIR / "lyrics.txt"
STYLE_PATH = DESKTOP_DIR / "style.txt"
AUDIO_PATH = DESKTOP_DIR / "Twinkle_Twinkle_Little_Star_Rich.mp3"
VIDEO_PATH = DESKTOP_DIR / "Twinkle_Twinkle_Little_Star_Rich_Shorts.mp4"
MANIFEST_PATH = DESKTOP_DIR / "manifest.json"


def _nvidia_generate_kids_rhyme(settings: Settings, prompt: str, singer_gender: str, language: str) -> tuple[str, str]:
    system_instruction = (
        "You are a children's song and nursery rhyme composer. Expand the kids' song idea into complete lyrics and style description. "
        "The output must be JSON with keys 'lyrics' and 'style'."
    )
    user_prompt = f"""
User Kids Song Idea: "{prompt}"
Singer Voice Gender Selection: "{singer_gender}"
Target Song Language: "{language}"

Requirements:
1. If the Target Song Language is 'English', write the lyrics in English.
2. Honor every explicit instruction inside the User Kids Song Idea, especially song speed, rhythm, mood, topic, language, verse count, chorus repetition, and any latest user advice.
3. If the prompt includes a Song speed line, follow it exactly and shape the rhyme around that speed instead of exact duration.
4. Structure the lyrics with standard tags like [verse] and [chorus]. Avoid [intro] or [outro] tags. Use the selected speed to decide line density, hook repetition, and pacing.
5. The 'style' string must be a comma-separated description of instruments, tempo (BPM), vocal qualities, and musical genre suitable for kids/toddlers.

Return a raw JSON object matching this schema:
{{
    "lyrics": "verse and chorus text",
    "style": "comma-separated musical style description"
}}
""".strip()

    keys = list(settings.nvidia_api_keys)
    if not keys and settings.nvidia_api_key:
        keys = [settings.nvidia_api_key]
    if os.environ.get("NVIDIA_API_KEY") and os.environ.get("NVIDIA_API_KEY") not in keys:
        keys.insert(0, os.environ.get("NVIDIA_API_KEY"))
    keys = [k for k in keys if k]
    if not keys:
        raise RuntimeError("No NVIDIA_API_KEY found for script generation.")

    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    last_error = None
    for key in keys:
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "meta/llama-3.3-70b-instruct",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1200,
                    "response_format": {"type": "json_object"},
                },
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if "lyrics" in parsed and "style" in parsed:
                return str(parsed["lyrics"]).strip(), str(parsed["style"]).strip()
            last_error = f"Invalid JSON: {content[:200]}"
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(f"NVIDIA lyric generation failed: {last_error}")


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

    topic = "Twinkle Twinkle Little Star"
    language = "English"
    singer_key = "EN_RHYME_ANA_CLEAR"
    singer_gender = "Female"
    song_speed = "Mid"

    prompt = (
        f'Create a nursery rhyme / poem from this idea: "{topic}".\n'
        f"Song speed: {song_speed}.\n"
        "Speed direction: Use balanced pacing, clean hooks, steady repetition, and an easy sing-along flow.\n"
        "Musical pace target: 92 BPM.\n"
        "Do not mention exact song length or duration in the generated rhyme. Shape the rhyme only by speed, rhythm, and repetition.\n"
        f"Target language: {language}.\n"
        "Voice feel: friendly Female voice for toddlers and kids.\n"
        "Structure: Use [verse] and [chorus] tags, simple rhyming couplets, repeatable rhythm, and child-safe imagery.\n"
        "Also return a matching music/style description for the audio generator."
    )

    lyrics, style = _nvidia_generate_kids_rhyme(settings, prompt, singer_gender, language)
    PROMPT_PATH.write_text(prompt, encoding="utf-8")
    LYRICS_PATH.write_text(lyrics, encoding="utf-8")
    STYLE_PATH.write_text(style, encoding="utf-8")

    voice_key = SINGER_ALIASES.get(singer_key, singer_key)
    if voice_key not in SINGER_MANIFEST:
        raise RuntimeError(f"Unknown voice profile: {singer_key}")

    generate_hindi_song_via_native_audio(
        lyrics=lyrics,
        output_path=AUDIO_PATH,
        singer_gender=singer_gender,
        selected_ref="None (Text-only)",
        hf_token=settings.hf_token,
        genre="Pop",
        temperature=0.35,
        cfg_coef=1.8,
        style_description=style,
        singer_key=singer_key,
        mode="Poem/Rhyme",
    )

    _make_short_video(IMAGE_PATH, AUDIO_PATH, VIDEO_PATH)

    manifest = {
        "topic": topic,
        "language": language,
        "script_generator": "NVIDIA Llama 3.3",
        "voice_profile": singer_key,
        "song_speed": song_speed,
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
