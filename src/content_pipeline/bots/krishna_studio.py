from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import date
from html import escape
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ManualVideoScene:
    id: str
    title: str
    duration_seconds: int
    narration_hi: str
    on_screen_text_hi: str
    openart_prompt: str
    meta_prompt: str
    expected_clip_file: str


@dataclass(frozen=True)
class ManualVideoEpisode:
    episode_id: str
    title_hi: str
    title_en: str
    description_hi: str
    target_duration_seconds: int
    aspect: str
    width: int
    height: int
    audience: str
    scenes: list[ManualVideoScene]
    safety_rules: list[str]
    youtube_title: str
    youtube_description: str
    hashtags: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "title_hi": self.title_hi,
            "title_en": self.title_en,
            "description_hi": self.description_hi,
            "target_duration_seconds": self.target_duration_seconds,
            "aspect": self.aspect,
            "width": self.width,
            "height": self.height,
            "audience": self.audience,
            "scenes": [asdict(scene) for scene in self.scenes],
            "safety_rules": self.safety_rules,
            "youtube_title": self.youtube_title,
            "youtube_description": self.youtube_description,
            "hashtags": self.hashtags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManualVideoEpisode":
        return cls(
            episode_id=data["episode_id"],
            title_hi=data["title_hi"],
            title_en=data["title_en"],
            description_hi=data["description_hi"],
            target_duration_seconds=int(data["target_duration_seconds"]),
            aspect=data.get("aspect", "shorts"),
            width=int(data.get("width", 720)),
            height=int(data.get("height", 1280)),
            audience=data["audience"],
            scenes=[ManualVideoScene(**scene) for scene in data["scenes"]],
            safety_rules=list(data["safety_rules"]),
            youtube_title=data["youtube_title"],
            youtube_description=data["youtube_description"],
            hashtags=list(data["hashtags"]),
        )


def butter_heist_short_episode(
    episode_date: str | None = None,
    aspect: str = "shorts",
) -> ManualVideoEpisode:
    if aspect not in {"shorts", "landscape"}:
        raise ValueError("aspect must be 'shorts' or 'landscape'.")
    day = episode_date or date.today().isoformat()
    aspect_label = "Landscape 16:9" if aspect == "landscape" else "Vertical 9:16"
    width, height = (1280, 720) if aspect == "landscape" else (720, 1280)
    framing = (
        "wide cinematic YouTube frame with characters fully visible and extra Gokul background space"
        if aspect == "landscape"
        else "mobile Shorts frame with the subject centered and readable on a phone screen"
    )
    style = (
        f"{aspect_label}, {framing}, original bright 3D Indian children's animation, warm Gokul village, "
        "expressive fictional toddler Kanha with soft blue-toned skin, curly hair, one peacock "
        "feather, yellow dhoti, red waistband; fictional Yashoda in orange sari with magenta "
        "border. Child-safe devotional comedy, no copied studio style, no copyrighted character, "
        "no real-person likeness, no text, no logo, no watermark."
    )
    motion = (
        "Smooth gentle camera motion, natural blinking, soft smile, moving tree leaves, drifting "
        "clouds, marigold garlands swaying, butter pot swinging lightly."
    )
    return ManualVideoEpisode(
        episode_id=f"{day}_makhan_ki_matki_{aspect}",
        title_hi="कान्हा और माखन की मटकी",
        title_en="Kanha and the Butter Pot",
        description_hi=(
            "एक प्यारी बाल लीला जहां नन्हे कान्हा माखन की मटकी देखकर मुस्कुराते हैं, "
            "दोस्तों के साथ मिलकर उपाय सोचते हैं, और अंत में मैया यशोदा प्यार से उन्हें "
            "सीख देती हैं कि खुशी बांटने से बढ़ती है।"
        ),
        target_duration_seconds=64,
        aspect=aspect,
        width=width,
        height=height,
        audience="Kids and family devotional storytelling",
        scenes=[
            ManualVideoScene(
                id="scene_01",
                title="गोकुल की सुबह",
                duration_seconds=7,
                narration_hi=(
                    "गोकुल की सुनहरी सुबह थी। आंगन में फूलों की खुशबू थी, और ऊपर लटक रही थी "
                    "माखन से भरी एक छोटी सी मटकी।"
                ),
                on_screen_text_hi="गोकुल की सुनहरी सुबह",
                openart_prompt=f"{style} {motion} Wide establishing shot of a cheerful Gokul courtyard at sunrise, decorated hanging butter pot, rangoli, marigolds, leafy tree, peaceful cows in far background.",
                meta_prompt=f"{style} {motion} Create a 7 second {aspect_label} animated shot: cheerful Gokul courtyard sunrise, hanging butter pot sways gently, leaves and clouds move softly.",
                expected_clip_file="scene_01.mp4",
            ),
            ManualVideoScene(
                id="scene_02",
                title="कान्हा की नज़र",
                duration_seconds=8,
                narration_hi=(
                    "नन्हे कान्हा ने मटकी को देखा। उनकी आंखें चमक उठीं, जैसे कोई प्यारा सा "
                    "विचार उनके मन में नाचने लगा हो।"
                ),
                on_screen_text_hi="कान्हा ने मटकी देखी...",
                openart_prompt=f"{style} {motion} Medium shot: Kanha safely standing on courtyard floor, looking up at hanging butter pot, blinking once, then smiling playfully. No climbing, no danger.",
                meta_prompt=f"{style} {motion} Animate Kanha looking up at a butter pot, eyes brighten, one blink, gentle mischievous smile, safe courtyard floor.",
                expected_clip_file="scene_02.mp4",
            ),
            ManualVideoScene(
                id="scene_03",
                title="दोस्तों की योजना",
                duration_seconds=8,
                narration_hi=(
                    "कान्हा ने अपने दोस्तों को इशारा किया। सब धीरे से पास आए और बोले, "
                    "मटकी ऊंची है, पर मिलकर कोशिश करेंगे।"
                ),
                on_screen_text_hi="टीमवर्क से काम आसान",
                openart_prompt=f"{style} {motion} Three fictional cowherd children gather around Kanha, pointing gently at the butter pot and planning together, cheerful expressions, no unsafe climbing yet.",
                meta_prompt=f"{style} {motion} Kanha and friends make a playful plan under the butter pot, smiling, pointing upward, garlands moving in breeze.",
                expected_clip_file="scene_03.mp4",
            ),
            ManualVideoScene(
                id="scene_04",
                title="माखन की खुशबू",
                duration_seconds=7,
                narration_hi=(
                    "इतने में माखन की खुशबू हवा में फैल गई। पास बैठे बंदर भी उत्सुक होकर "
                    "देखने लगे।"
                ),
                on_screen_text_hi="माखन की खुशबू!",
                openart_prompt=f"{style} {motion} Close-up of decorated clay butter pot with fresh white butter at rim, peacock feather nearby, small friendly monkeys watching from tree branch, cute and gentle.",
                meta_prompt=f"{style} {motion} Close-up butter pot, creamy butter visible, peacock feather, friendly monkeys on branch, warm sunlight, 7 second {aspect_label} animation.",
                expected_clip_file="scene_04.mp4",
            ),
            ManualVideoScene(
                id="scene_05",
                title="मटकी झूली",
                duration_seconds=8,
                narration_hi=(
                    "कान्हा ने हाथ बढ़ाया, मटकी हल्की सी झूली, और सब बच्चे हंस पड़े। "
                    "कभी-कभी खेल भी सीख बन जाता है।"
                ),
                on_screen_text_hi="खेल में भी सीख",
                openart_prompt=f"{style} {motion} Kanha reaches toward a low decorative butter pot while standing safely, pot swings lightly, children laugh, sparkles of joy, no breaking, no falling.",
                meta_prompt=f"{style} {motion} Safe playful action: Kanha reaches toward low butter pot, it swings softly, children laugh, no danger, no broken pot.",
                expected_clip_file="scene_05.mp4",
            ),
            ManualVideoScene(
                id="scene_06",
                title="यशोदा आईं",
                duration_seconds=8,
                narration_hi=(
                    "मैया यशोदा ने आकर मुस्कुराते हुए पूछा, कान्हा, फिर से माखन? कान्हा ने "
                    "भोली आंखों से देखा और सब हंसने लगे।"
                ),
                on_screen_text_hi="मैया यशोदा आईं",
                openart_prompt=f"{style} {motion} Yashoda enters courtyard smiling kindly, Kanha looks innocent with butter on finger, children giggle softly, warm motherly emotion.",
                meta_prompt=f"{style} {motion} Yashoda arrives smiling, Kanha innocent expression with tiny butter on finger, children giggle, warm family comedy.",
                expected_clip_file="scene_06.mp4",
            ),
            ManualVideoScene(
                id="scene_07",
                title="प्यार भरी सीख",
                duration_seconds=10,
                narration_hi=(
                    "यशोदा ने कान्हा को गले लगाकर कहा, बेटा, माखन मीठा है, लेकिन बांटकर "
                    "खाने की खुशी उससे भी मीठी होती है।"
                ),
                on_screen_text_hi="बांटने से खुशी बढ़ती है",
                openart_prompt=f"{style} {motion} Emotional shot: Yashoda gently hugs Kanha, both smiling, soft golden light, leaves moving, peaceful devotional warmth, no tears, no sadness.",
                meta_prompt=f"{style} {motion} Yashoda hugs Kanha gently, warm golden sunlight, soft smiles, emotional family-friendly ending.",
                expected_clip_file="scene_07.mp4",
            ),
            ManualVideoScene(
                id="scene_08",
                title="सबने माखन बांटा",
                duration_seconds=8,
                narration_hi=(
                    "फिर कान्हा ने माखन सब दोस्तों और बंदरों में बांट दिया। उस दिन गोकुल "
                    "में सबसे मीठी चीज माखन नहीं, सबकी मुस्कान थी।"
                ),
                on_screen_text_hi="मोरल: खुशी बांटो",
                openart_prompt=f"{style} {motion} Closing joyful shot: Kanha shares butter with friends and friendly monkeys in courtyard, everyone smiling, flower petals drift, uplifting ending.",
                meta_prompt=f"{style} {motion} Kanha shares butter with friends and monkeys, everyone smiling, petals drifting, bright devotional closing shot.",
                expected_clip_file="scene_08.mp4",
            ),
        ],
        safety_rules=[
            "Use only fictional character designs; do not upload family photographs as character references.",
            "Do not imitate named animation studios, copyrighted cartoons, movie stills or famous devotional artwork.",
            "Use only generated, licensed or self-owned music and sound effects.",
            "Disclose AI-generated visuals and AI-generated narration in the video description.",
            "Set YouTube audience as Made for Kids when publishing child-directed Bal Leela content.",
            "Do not remove provider watermarks unless the provider's terms explicitly allow watermark-free export.",
            "Treat Meta AI commercial usage as unconfirmed until its current terms for the exact feature are reviewed.",
        ],
        youtube_title="कान्हा और माखन की मटकी | Bal Krishna Story for Kids | Hindi Animation",
        youtube_description=(
            "नन्हे कान्हा की प्यारी बाल लीला: माखन की मटकी, दोस्ती, हंसी और बांटने की सीख।\n\n"
            "Moral: खुशी बांटने से बढ़ती है।\n\n"
            "Disclosure: इस वीडियो में AI-generated visuals और AI-generated narration का उपयोग किया गया है। "
            "Characters are original fictional designs, not real-person likenesses."
        ),
        hashtags=["#BalKrishna", "#KrishnaStory", "#HindiStories", "#KidsAnimation", "#Kanha"],
    )


def create_daily_video_workspace(output_dir: Path, episode: ManualVideoEpisode | None = None) -> list[Path]:
    episode = episode or butter_heist_short_episode()
    root = output_dir / "kanha_ki_nanhi_leela" / "episodes" / episode.episode_id
    inbox = root / "clips" / "inbox"
    review = root / "video"
    ui = root / "ui"
    for directory in (inbox, review, ui):
        directory.mkdir(parents=True, exist_ok=True)
    (inbox / ".gitkeep").write_text("", encoding="utf-8")

    episode_path = root / "episode.json"
    episode_path.write_text(json.dumps(episode.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    script_path = root / "story_script.md"
    script_path.write_text(_story_markdown(episode), encoding="utf-8")

    prompts_path = root / "scene_prompts.json"
    prompts_path.write_text(_prompts_json(episode), encoding="utf-8")

    metadata_path = root / "youtube_metadata.md"
    metadata_path.write_text(_metadata_markdown(episode), encoding="utf-8")

    guide_path = root / "clip_drop_guide.md"
    guide_path.write_text(_clip_drop_guide(episode), encoding="utf-8")

    ui_path = ui / "index.html"
    ui_path.write_text(_episode_dashboard_html(episode, root), encoding="utf-8")
    return [episode_path, script_path, prompts_path, metadata_path, guide_path, ui_path]


def assemble_manual_episode(workspace_dir: Path) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to assemble downloaded OpenArt or Meta AI clips.")
    episode = ManualVideoEpisode.from_dict(
        json.loads((workspace_dir / "episode.json").read_text(encoding="utf-8"))
    )
    inbox = workspace_dir / "clips" / "inbox"
    missing = [
        scene.expected_clip_file
        for scene in episode.scenes
        if not (inbox / scene.expected_clip_file).exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Downloaded clips are missing from clips/inbox: " + ", ".join(missing)
        )
    normalized_dir = workspace_dir / "clips" / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    normalized_paths: list[Path] = []
    for scene in episode.scenes:
        source = inbox / scene.expected_clip_file
        destination = normalized_dir / scene.expected_clip_file
        subprocess.run(
            [
                executable,
                "-y",
                "-i",
                str(source),
                "-vf",
                (
                    f"scale={episode.width}:{episode.height}:force_original_aspect_ratio=decrease,"
                    f"pad={episode.width}:{episode.height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
                ),
                "-r",
                "25",
                "-an",
                "-c:v",
                "libx264",
                "-movflags",
                "+faststart",
                str(destination),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        normalized_paths.append(destination)

    video_dir = workspace_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    concat_path = video_dir / "manual_clips.txt"
    concat_path.write_text(
        "\n".join(f"file '{path}'" for path in normalized_paths) + "\n",
        encoding="utf-8",
    )
    output_path = video_dir / "assembled_review.mp4"
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    (video_dir / "subtitles_hi.srt").write_text(_subtitle_srt(episode), encoding="utf-8")
    return output_path


def _story_markdown(episode: ManualVideoEpisode) -> str:
    lines = [
        f"# {episode.title_hi}",
        "",
        f"**English:** {episode.title_en}",
        f"**Duration target:** {episode.target_duration_seconds} seconds",
        f"**Format:** {episode.aspect} ({episode.width}x{episode.height})",
        f"**Audience:** {episode.audience}",
        "",
        episode.description_hi,
        "",
        "## Narration Script",
        "",
    ]
    for index, scene in enumerate(episode.scenes, start=1):
        lines.extend(
            [
                f"### {index}. {scene.title}",
                "",
                scene.narration_hi,
                "",
                f"On screen: {scene.on_screen_text_hi}",
                "",
            ]
        )
    lines.extend(["## Safety Rules", "", *[f"- {rule}" for rule in episode.safety_rules], ""])
    return "\n".join(lines)


def _prompts_json(episode: ManualVideoEpisode) -> str:
    prompts = [
        {
            "scene": scene.id,
            "title": scene.title,
            "duration_seconds": scene.duration_seconds,
            "aspect": episode.aspect,
            "size": f"{episode.width}x{episode.height}",
            "expected_clip_file": scene.expected_clip_file,
            "openart_prompt": scene.openart_prompt,
            "meta_ai_prompt": scene.meta_prompt,
        }
        for scene in episode.scenes
    ]
    return json.dumps(prompts, indent=2, ensure_ascii=False) + "\n"


def _metadata_markdown(episode: ManualVideoEpisode) -> str:
    return "\n".join(
        [
            f"# {episode.youtube_title}",
            "",
            "## Description",
            "",
            episode.youtube_description,
            "",
            "## Hashtags",
            "",
            " ".join(episode.hashtags),
            "",
        ]
    )


def _clip_drop_guide(episode: ManualVideoEpisode) -> str:
    lines = [
        "# Clip Drop Guide",
        "",
        "Generate each scene manually in OpenArt or Meta AI, download the MP4, then rename it exactly:",
        "",
        f"Target format: `{episode.aspect}` / `{episode.width}x{episode.height}`",
        "",
    ]
    for scene in episode.scenes:
        lines.append(f"- `{scene.expected_clip_file}` - {scene.title} ({scene.duration_seconds}s)")
    lines.extend(
        [
            "",
            "Place all files in:",
            "",
            "`clips/inbox/`",
            "",
            "Then run:",
            "",
            "```bash",
            "PYTHONPATH=src .venv/bin/python -m content_pipeline krishna-manual-video-assemble --workspace <episode_workspace>",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _episode_dashboard_html(episode: ManualVideoEpisode, root: Path) -> str:
    scene_cards = "\n".join(_scene_card(scene, index) for index, scene in enumerate(episode.scenes, start=1))
    rules = "\n".join(f"<li>{escape(rule)}</li>" for rule in episode.safety_rules)
    description = escape(episode.youtube_description)
    hashtags = escape(" ".join(episode.hashtags))
    return f"""<!doctype html>
<html lang="hi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(episode.title_hi)} - Daily Video Studio</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #13091f; color: #fff7ec; }}
    header {{ padding: 34px; background: linear-gradient(135deg, #31135c, #8f3d1b); }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }}
    .card {{ background: #211030; border: 1px solid #6a3f79; border-radius: 18px; padding: 18px; box-shadow: 0 16px 44px rgba(0,0,0,.28); }}
    .scene {{ border-left: 5px solid #ffc05a; }}
    h1, h2, h3 {{ margin: 0 0 10px; }}
    p, li {{ line-height: 1.55; color: #f4dfcf; }}
    textarea {{ width: 100%; min-height: 210px; box-sizing: border-box; border-radius: 12px; border: 1px solid #8c6798; padding: 12px; background: #100817; color: #fff9ef; }}
    button {{ background: #ffc05a; color: #1a0b22; border: 0; border-radius: 999px; padding: 9px 14px; font-weight: 700; cursor: pointer; }}
    code {{ color: #ffd27a; }}
    .muted {{ color: #d3b8c9; }}
    .pill {{ display: inline-block; margin: 3px 6px 3px 0; padding: 5px 10px; border-radius: 999px; background: #41214f; color: #ffe1aa; font-size: 13px; }}
  </style>
</head>
<body>
  <header>
    <div class="pill">Manual OpenArt / Meta AI Workflow</div>
    <div class="pill">{escape(episode.aspect)} - {episode.width}x{episode.height}</div>
    <h1>{escape(episode.title_hi)}</h1>
    <p>{escape(episode.description_hi)}</p>
    <p class="muted">Workspace: <code>{escape(str(root))}</code></p>
  </header>
  <main>
    <section class="grid">
      <div class="card">
        <h2>Today&apos;s Flow</h2>
        <p>1. Read script. 2. Copy scene prompts into OpenArt or Meta AI. 3. Select <strong>{episode.width}x{episode.height}</strong> / <strong>{escape(episode.aspect)}</strong> when possible. 4. Download each MP4. 5. Rename files as shown. 6. Drop them into <code>clips/inbox</code>. 7. Run assembly.</p>
      </div>
      <div class="card">
        <h2>YouTube Metadata</h2>
        <p><strong>{escape(episode.youtube_title)}</strong></p>
        <textarea id="metadata">{description}\n\n{hashtags}</textarea>
        <button onclick="copyText('metadata')">Copy Metadata</button>
      </div>
      <div class="card">
        <h2>Policy Notes</h2>
        <ul>{rules}</ul>
      </div>
    </section>
    <h2 style="margin-top: 30px;">Scene Prompts</h2>
    <section class="grid">{scene_cards}</section>
  </main>
  <script>
    function copyText(id) {{
      const el = document.getElementById(id);
      el.select();
      navigator.clipboard.writeText(el.value);
    }}
  </script>
</body>
</html>
"""


def _scene_card(scene: ManualVideoScene, index: int) -> str:
    openart_id = f"openart_{index:02d}"
    meta_id = f"meta_{index:02d}"
    return f"""<article class="card scene">
  <div class="pill">Scene {index:02d} - {scene.duration_seconds}s - save as {escape(scene.expected_clip_file)}</div>
  <h3>{escape(scene.title)}</h3>
  <p><strong>Narration:</strong> {escape(scene.narration_hi)}</p>
  <p><strong>On screen:</strong> {escape(scene.on_screen_text_hi)}</p>
  <label>OpenArt prompt</label>
  <textarea id="{openart_id}">{escape(scene.openart_prompt)}</textarea>
  <button onclick="copyText('{openart_id}')">Copy OpenArt Prompt</button>
  <br><br>
  <label>Meta AI prompt</label>
  <textarea id="{meta_id}">{escape(scene.meta_prompt)}</textarea>
  <button onclick="copyText('{meta_id}')">Copy Meta Prompt</button>
</article>"""


def _subtitle_srt(episode: ManualVideoEpisode) -> str:
    lines: list[str] = []
    start = 0
    for index, scene in enumerate(episode.scenes, start=1):
        end = start + scene.duration_seconds
        lines.extend(
            [
                str(index),
                f"{_timestamp(start)} --> {_timestamp(end)}",
                scene.narration_hi,
                "",
            ]
        )
        start = end
    return "\n".join(lines)


def _timestamp(seconds: int) -> str:
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},000"
