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
class CharacterReference:
    id: str
    name: str
    role: str
    description: str
    reference_prompt: str
    image_file: str


@dataclass(frozen=True)
class StoryScene:
    id: str
    title: str
    duration_seconds: int
    narration: str
    on_screen_text: str
    visual_mode: str
    openart_prompt: str
    meta_prompt: str
    expected_clip_file: str


@dataclass(frozen=True)
class StoryEpisode:
    episode_id: str
    audience: str
    aspect: str
    width: int
    height: int
    title: str
    logline: str
    target_duration_seconds: int
    story_source: str
    characters: list[CharacterReference]
    scenes: list[StoryScene]
    production_notes: list[str]
    safety_rules: list[str]
    youtube_title: str
    youtube_description: str
    hashtags: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "audience": self.audience,
            "aspect": self.aspect,
            "width": self.width,
            "height": self.height,
            "title": self.title,
            "logline": self.logline,
            "target_duration_seconds": self.target_duration_seconds,
            "story_source": self.story_source,
            "characters": [asdict(character) for character in self.characters],
            "scenes": [asdict(scene) for scene in self.scenes],
            "production_notes": self.production_notes,
            "safety_rules": self.safety_rules,
            "youtube_title": self.youtube_title,
            "youtube_description": self.youtube_description,
            "hashtags": self.hashtags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StoryEpisode":
        return cls(
            episode_id=data["episode_id"],
            audience=data["audience"],
            aspect=data["aspect"],
            width=int(data["width"]),
            height=int(data["height"]),
            title=data["title"],
            logline=data["logline"],
            target_duration_seconds=int(data["target_duration_seconds"]),
            story_source=data["story_source"],
            characters=[CharacterReference(**character) for character in data.get("characters", [])],
            scenes=[StoryScene(**scene) for scene in data["scenes"]],
            production_notes=list(data["production_notes"]),
            safety_rules=list(data["safety_rules"]),
            youtube_title=data["youtube_title"],
            youtube_description=data["youtube_description"],
            hashtags=list(data["hashtags"]),
        )


def create_story_episode(
    audience: str,
    idea: str | None = None,
    episode_date: str | None = None,
    aspect: str = "shorts",
) -> StoryEpisode:
    if audience not in {"kid", "adult"}:
        raise ValueError("audience must be 'kid' or 'adult'.")
    if aspect not in {"shorts", "landscape"}:
        raise ValueError("aspect must be 'shorts' or 'landscape'.")
    day = episode_date or date.today().isoformat()
    width, height = (1280, 720) if aspect == "landscape" else (720, 1280)
    if audience == "kid":
        return _kid_episode(day, idea, aspect, width, height)
    return _adult_episode(day, idea, aspect, width, height)


def create_story_workspace(
    output_dir: Path,
    episode: StoryEpisode,
) -> list[Path]:
    root = output_dir / "story_studio" / "episodes" / episode.episode_id
    inbox = root / "clips" / "inbox"
    video = root / "video"
    ui = root / "ui"
    for directory in (inbox, video, ui):
        directory.mkdir(parents=True, exist_ok=True)
    (inbox / ".gitkeep").write_text("", encoding="utf-8")

    paths = [
        _write_json(root / "episode.json", episode.as_dict()),
        _write_json(root / "characters" / "character_references.json", [asdict(character) for character in episode.characters]),
        _write_text(root / "story_script.md", _script_markdown(episode)),
        _write_json(root / "scene_prompts.json", _prompt_rows(episode)),
        _write_text(root / "clip_drop_guide.md", _clip_drop_guide(episode)),
        _write_text(root / "youtube_metadata.md", _metadata_markdown(episode)),
    ]
    for character in episode.characters:
        paths.append(_write_text(root / character.image_file, _character_svg(character)))
    bank = update_story_bank(output_dir, episode)
    paths.append(bank)
    recent = recent_stories(output_dir)
    paths.append(_write_text(ui / "index.html", _dashboard_html(episode, root, recent)))
    return paths


def update_story_bank(output_dir: Path, episode: StoryEpisode) -> Path:
    path = output_dir / "story_studio" / "story_bank.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8")).get("stories", [])
    row = {
        "episode_id": episode.episode_id,
        "title": episode.title,
        "audience": episode.audience,
        "aspect": episode.aspect,
        "created_on": date.today().isoformat(),
        "logline": episode.logline,
    }
    stories = [row, *[item for item in existing if item.get("episode_id") != episode.episode_id]][:3]
    path.write_text(json.dumps({"stories": stories}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def recent_stories(output_dir: Path) -> list[dict[str, str]]:
    path = output_dir / "story_studio" / "story_bank.json"
    if not path.exists():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("stories", []))[:3]


def assemble_story_episode(workspace_dir: Path) -> Path:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise RuntimeError("FFmpeg is required to assemble story clips.")
    episode = StoryEpisode.from_dict(json.loads((workspace_dir / "episode.json").read_text(encoding="utf-8")))
    inbox = workspace_dir / "clips" / "inbox"
    missing = [
        scene.expected_clip_file
        for scene in episode.scenes
        if not (inbox / scene.expected_clip_file).exists()
    ]
    if missing:
        raise FileNotFoundError("Downloaded clips are missing from clips/inbox: " + ", ".join(missing))

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
    concat_path = video_dir / "story_clips.txt"
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
    (video_dir / "subtitles.srt").write_text(_subtitle_srt(episode), encoding="utf-8")
    return output_path


def _kid_episode(day: str, idea: str | None, aspect: str, width: int, height: int) -> StoryEpisode:
    source = idea.strip() if idea else "auto-created: sharing toys"
    title = "Golu Shares His Toys" if not idea else _title_from_idea(source, fallback="Golu Learns Something New")
    aspect_label = "Landscape 16:9" if aspect == "landscape" else "Vertical 9:16"
    style = (
        f"{aspect_label}, original bright 3D cartoon for 2 to 5 year old children, soft rounded shapes, "
        "warm nursery colors, simple expressive faces, gentle motion, no scary visuals, no violence, "
        "no copyrighted characters, no text, logo or watermark."
    )
    characters = [
        CharacterReference(
            "golu_v1",
            "Golu",
            "main character",
            "A round baby elephant with soft blue-gray skin, big kind eyes, tiny yellow scarf, small red toy-car badge, cheerful toddler expressions.",
            (
                "Create a clean character reference sheet for Golu V1, a round baby elephant for an original "
                "2-5 kids cartoon: soft blue-gray skin, big kind eyes, tiny yellow scarf, small red toy-car badge, "
                "front view, side view, happy face, thoughtful face, simple shapes, no text, no logo."
            ),
            "characters/golu_v1_reference.svg",
        ),
        CharacterReference(
            "mimi_v1",
            "Mimi",
            "friend",
            "A tiny yellow bird with orange feet, small teal bow, round friendly eyes, soft preschool cartoon proportions.",
            (
                "Create a clean character reference sheet for Mimi V1, a tiny yellow bird friend for an original "
                "2-5 kids cartoon: orange feet, small teal bow, round friendly eyes, happy pose, curious pose, "
                "simple soft shapes, no text, no logo."
            ),
            "characters/mimi_v1_reference.svg",
        ),
    ]
    character_lock = _character_lock(characters)
    scenes = [
        StoryScene(
            "scene_01",
            "Golu's Toy Box",
            7,
            "Golu had a red car, a yellow ball, and a tiny train. He loved them all very much.",
            "Golu's toys",
            "motion_video",
            f"{style} {character_lock} Cute baby elephant Golu sits near a colorful toy box, red car, yellow ball and tiny train wiggle gently, happy playroom, camera slowly pushes in.",
            f"{style} {character_lock} 7 second animated scene: cute baby elephant with toy box, toys move gently, cheerful playroom.",
            "scene_01.mp4",
        ),
        StoryScene(
            "scene_02",
            "Mimi Wants To Play",
            8,
            "Mimi came and asked, Golu, can I play too? Golu hugged his toys and said, Mine.",
            "Can I play too?",
            "motion_video",
            f"{style} {character_lock} Small friendly bird Mimi asks to play, Golu gently hugs his toys, no anger, just toddler emotion, soft funny expressions.",
            f"{style} {character_lock} 8 second animated scene: little bird asks to play, baby elephant holds toys, gentle toddler emotion.",
            "scene_02.mp4",
        ),
        StoryScene(
            "scene_03",
            "Playing Alone Feels Small",
            8,
            "Golu played alone. The car went vroom, the ball went bounce, but Golu did not laugh.",
            "Alone is not so fun",
            "motion_video",
            f"{style} {character_lock} Golu plays alone with toy car and ball, toys move but the room feels quiet, Golu looks thoughtful, still safe and soft.",
            f"{style} {character_lock} 8 second animated scene: baby elephant plays alone, toy car moves, ball bounces, quiet feeling.",
            "scene_03.mp4",
        ),
        StoryScene(
            "scene_04",
            "A Small Idea",
            8,
            "Then Golu had a small idea. Maybe toys become happier when friends play together.",
            "A kind idea",
            "motion_video",
            f"{style} {character_lock} Golu's face brightens with a kind idea, soft sparkle, Mimi waits nearby, toy train gently rolls between them.",
            f"{style} {character_lock} 8 second animated scene: baby elephant smiles with an idea, toy train rolls, friend waits nearby.",
            "scene_04.mp4",
        ),
        StoryScene(
            "scene_05",
            "Sharing Time",
            9,
            "Golu gave Mimi the yellow ball. Mimi smiled. Golu smiled too.",
            "Sharing time",
            "motion_video",
            f"{style} {character_lock} Golu gently gives yellow ball to Mimi, both smile, ball bounces once, warm happy motion.",
            f"{style} {character_lock} 9 second animated scene: baby elephant shares yellow ball with little bird, both smile, ball bounces.",
            "scene_05.mp4",
        ),
        StoryScene(
            "scene_06",
            "Playtime Becomes Bigger",
            9,
            "Now the car went vroom, the ball went bounce, and the room was full of giggles.",
            "Sharing makes play happy",
            "motion_video",
            f"{style} {character_lock} Golu and Mimi play together, red car rolls safely, yellow ball bounces softly, colorful toy room full of smiles.",
            f"{style} {character_lock} 9 second animated scene: friends play together with toy car and ball, happy giggles, safe motion.",
            "scene_06.mp4",
        ),
        StoryScene(
            "scene_07",
            "Moral",
            7,
            "Golu learned: toys are fun, but sharing makes playtime happier.",
            "Moral: Share with love",
            "motion_video",
            f"{style} {character_lock} Closing shot: Golu and Mimi wave together beside toy box, soft confetti shapes drift, warm bedtime-story ending.",
            f"{style} {character_lock} 7 second closing animation: baby elephant and bird wave, toys neatly placed, warm happy ending.",
            "scene_07.mp4",
        ),
    ]
    return StoryEpisode(
        episode_id=f"{day}_{_slug(title)}_{aspect}",
        audience="kid",
        aspect=aspect,
        width=width,
        height=height,
        title=title,
        logline="A gentle 2-5 story about sharing toys and feeling happy together.",
        target_duration_seconds=sum(scene.duration_seconds for scene in scenes),
        story_source=source,
        characters=characters,
        scenes=scenes,
        production_notes=[
            "For kids, use motion on every scene: blinking, smiles, toy movement, camera drift, leaves/clouds/sparkles.",
            "Keep narration simple, repetitive and emotionally safe.",
            "Avoid falling, danger, loud conflict, monsters and fast cuts for 2-5 year olds.",
        ],
        safety_rules=[
            "Use original characters only; no copyrighted cartoon or studio imitation.",
            "No frightening scenes, realistic injury, weapons or intense peril.",
            "Use licensed/self-owned music and disclose AI visuals or narration.",
            "Mark as Made for Kids if published for 2-5 year olds.",
        ],
        youtube_title=f"{title} | Sharing Story for Kids | 2-5 Years Cartoon",
        youtube_description=(
            "A gentle original story for toddlers and preschool kids.\n\n"
            "Moral: Sharing makes playtime happier.\n\n"
            "Disclosure: AI-generated visuals/narration may be used. Original fictional characters only."
        ),
        hashtags=["#KidsStories", "#ToddlerStories", "#Preschool", "#MoralStories", "#CartoonStories"],
    )


def _adult_episode(day: str, idea: str | None, aspect: str, width: int, height: int) -> StoryEpisode:
    source = idea.strip() if idea else "auto-created: stranded explorer on a silent moon"
    title = "The Signal Under the Ice" if not idea else _title_from_idea(source, fallback="The Last Signal")
    aspect_label = "Landscape 16:9" if aspect == "landscape" else "Vertical 9:16"
    style = (
        f"{aspect_label}, cinematic original adult science-fiction adventure, dramatic lighting, "
        "high-detail 2.5D illustrated frames, mature tone, no copyrighted franchise, no logo, no watermark."
    )
    characters = [
        CharacterReference(
            "ira_v1",
            "Commander Ira",
            "main character",
            "A determined adult space explorer in a matte white suit with cobalt trim, amber visor, triangular mission patch and compact shoulder light.",
            (
                "Create a cinematic character reference sheet for Commander Ira V1, an original adult sci-fi explorer: "
                "matte white suit, cobalt trim, amber visor, triangular mission patch, compact shoulder light, "
                "front view, side view, helmet close-up, no text, no logo."
            ),
            "characters/ira_v1_reference.svg",
        ),
    ]
    character_lock = _character_lock(characters)
    scenes = [
        StoryScene(
            "scene_01",
            "Silent Moon",
            8,
            "Commander Ira crossed the frozen moon alone, following a signal that should have died ten years ago.",
            "A dead signal wakes",
            "2_5d_image",
            f"{style} {character_lock} Wide shot of Commander Ira crossing blue-white frozen moon under a giant planet, subtle snow drift, 2.5D parallax image.",
            f"{style} {character_lock} 8 second cinematic shot: Commander Ira on frozen moon, slow camera move, snow drifting.",
            "scene_01.mp4",
        ),
        StoryScene(
            "scene_02",
            "The Crack Opens",
            8,
            "The ice split beneath her boots. Below it, an ancient city blinked with impossible green light.",
            "The city below",
            "motion_video",
            f"{style} {character_lock} Action scene: ice crack opens safely in front of Commander Ira, glowing underground alien city visible below, cinematic motion, no gore.",
            f"{style} {character_lock} 8 second action scene: ice opens, green alien city glows below, Commander Ira steps back safely.",
            "scene_02.mp4",
        ),
        StoryScene(
            "scene_03",
            "The Choice",
            10,
            "Her ship warned her to return. The signal whispered her name. Ira chose the unknown.",
            "Return or descend?",
            "2_5d_image",
            f"{style} {character_lock} Close cinematic shot of Commander Ira's amber helmet reflecting green underground city and distant ship warning lights, tense 2.5D parallax.",
            f"{style} {character_lock} 10 second shot: amber helmet reflection, green city, warning lights, slow dramatic push in.",
            "scene_03.mp4",
        ),
        StoryScene(
            "scene_04",
            "Descent",
            9,
            "She jumped into the blue dark, and gravity folded around her like a closing door.",
            "Into the unknown",
            "motion_video",
            f"{style} {character_lock} Creative motion scene: Commander Ira descends through glowing ice tunnel, light particles swirl, controlled fall, awe not horror.",
            f"{style} {character_lock} 9 second motion scene: Commander Ira falling through glowing ice tunnel, particles swirl, cinematic.",
            "scene_04.mp4",
        ),
        StoryScene(
            "scene_05",
            "The Message",
            10,
            "At the city's heart, she found no enemy. Only a map, and a warning: Earth was not alone.",
            "Earth was not alone",
            "2_5d_image",
            f"{style} {character_lock} Ancient alien chamber with star map hologram, Commander Ira standing small before huge glowing symbols, 2.5D parallax.",
            f"{style} {character_lock} 10 second cinematic shot: alien chamber, star map hologram, Commander Ira discovers warning.",
            "scene_05.mp4",
        ),
    ]
    return StoryEpisode(
        episode_id=f"{day}_{_slug(title)}_{aspect}",
        audience="adult",
        aspect=aspect,
        width=width,
        height=height,
        title=title,
        logline="A cinematic science-fiction micro story about a lonely explorer and a hidden warning.",
        target_duration_seconds=sum(scene.duration_seconds for scene in scenes),
        story_source=source,
        characters=characters,
        scenes=scenes,
        production_notes=[
            "For adult stories, use 2.5D images for atmosphere and save full motion video for action or discovery scenes.",
            "Adult genres can include sci-fi, war, kingdoms, mystery and adventure, but avoid graphic gore unless explicitly requested and policy-reviewed.",
            "Landscape is preferred for cinematic adult stories; Shorts can be used for teaser cuts.",
        ],
        safety_rules=[
            "Use original worlds, characters and symbols only; no franchise imitation.",
            "Do not use copyrighted music, movie stills or celebrity likenesses.",
            "Flag intense violence, horror or war themes for human review before generation.",
            "Disclose AI-generated visuals/narration when publishing.",
        ],
        youtube_title=f"{title} | Original Sci-Fi Short Story",
        youtube_description=(
            "An original cinematic short story for adult audiences.\n\n"
            "Disclosure: AI-generated visuals/narration may be used. Original fictional characters only."
        ),
        hashtags=["#SciFiStory", "#ShortStory", "#AIAnimation", "#CinematicStory", "#OriginalStory"],
    )


def _prompt_rows(episode: StoryEpisode) -> list[dict[str, Any]]:
    return [
        {
            "scene": scene.id,
            "title": scene.title,
            "duration_seconds": scene.duration_seconds,
            "visual_mode": scene.visual_mode,
            "aspect": episode.aspect,
            "size": f"{episode.width}x{episode.height}",
            "expected_clip_file": scene.expected_clip_file,
            "openart_prompt": scene.openart_prompt,
            "meta_ai_prompt": scene.meta_prompt,
        }
        for scene in episode.scenes
    ]


def _character_lock(characters: list[CharacterReference]) -> str:
    descriptions = " ".join(
        f"Keep {character.name} consistent as {character.description}" for character in characters
    )
    return f"Use the approved character reference designs. {descriptions}"


def _script_markdown(episode: StoryEpisode) -> str:
    lines = [
        f"# {episode.title}",
        "",
        f"**Audience:** {episode.audience}",
        f"**Format:** {episode.aspect} ({episode.width}x{episode.height})",
        f"**Story source:** {episode.story_source}",
        f"**Duration target:** {episode.target_duration_seconds} seconds",
        "",
        episode.logline,
        "",
        "## Character References",
        "",
    ]
    for character in episode.characters:
        lines.extend(
            [
                f"### {character.name}",
                "",
                character.description,
                "",
                f"Reference file: `{character.image_file}`",
                "",
                f"Reference prompt: {character.reference_prompt}",
                "",
            ]
        )
    lines.extend([
        "## Story",
        "",
    ])
    for index, scene in enumerate(episode.scenes, start=1):
        lines.extend(
            [
                f"### {index}. {scene.title}",
                "",
                f"Visual mode: `{scene.visual_mode}`",
                "",
                scene.narration,
                "",
                f"On screen: {scene.on_screen_text}",
                "",
            ]
        )
    lines.extend(["## Production Notes", "", *[f"- {note}" for note in episode.production_notes], ""])
    return "\n".join(lines)


def _clip_drop_guide(episode: StoryEpisode) -> str:
    lines = [
        "# Clip Drop Guide",
        "",
        f"Target: `{episode.audience}` / `{episode.aspect}` / `{episode.width}x{episode.height}`",
        "",
        "Generate/download each scene and rename exactly:",
        "",
    ]
    for scene in episode.scenes:
        lines.append(f"- `{scene.expected_clip_file}` - {scene.title} - `{scene.visual_mode}`")
    lines.extend(["", "Place all files in `clips/inbox/`, then run the assemble command.", ""])
    return "\n".join(lines)


def _metadata_markdown(episode: StoryEpisode) -> str:
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


def _dashboard_html(episode: StoryEpisode, root: Path, recent: list[dict[str, str]]) -> str:
    recent_options = "\n".join(
        f'<option value="{escape(item["episode_id"])}">{escape(item["title"])} - {escape(item["audience"])}</option>'
        for item in recent
    )
    cards = "\n".join(_scene_card(scene, index) for index, scene in enumerate(episode.scenes, start=1))
    character_cards = "\n".join(_character_card(character) for character in episode.characters)
    notes = "\n".join(f"<li>{escape(note)}</li>" for note in episode.production_notes)
    safety = "\n".join(f"<li>{escape(rule)}</li>" for rule in episode.safety_rules)
    current_command = (
        f"PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-create "
        f"--audience {episode.audience} --aspect {episode.aspect} --date 2026-05-28"
    )
    kid_command = (
        "PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-create "
        "--audience kid --aspect shorts --date 2026-05-28"
    )
    adult_command = (
        "PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-create "
        "--audience adult --aspect landscape --date 2026-05-28"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(episode.title)} - Story Studio</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #111827; color: #fff7ed; }}
    header {{ padding: 34px; background: linear-gradient(135deg, #1d4ed8, #9333ea); }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 18px; }}
    .card {{ background: #1f2937; border: 1px solid #475569; border-radius: 18px; padding: 18px; box-shadow: 0 14px 38px rgba(0,0,0,.25); }}
    .scene {{ border-left: 5px solid #fbbf24; }}
    textarea, select, input {{ width: 100%; box-sizing: border-box; border-radius: 12px; border: 1px solid #64748b; padding: 12px; background: #020617; color: #fff7ed; }}
    textarea {{ min-height: 190px; }}
    button {{ background: #fbbf24; color: #111827; border: 0; border-radius: 999px; padding: 9px 14px; font-weight: 700; cursor: pointer; }}
    code {{ color: #fde68a; }}
    .pill {{ display: inline-block; margin: 3px 6px 3px 0; padding: 5px 10px; border-radius: 999px; background: #312e81; color: #e0e7ff; font-size: 13px; }}
    .choice-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0 14px; }}
    .choice {{ border: 1px solid #64748b; border-radius: 14px; padding: 12px; background: #020617; }}
    .character-img {{ width: 100%; border-radius: 14px; background: #020617; border: 1px solid #64748b; }}
    .choice strong {{ display: block; margin-bottom: 4px; color: #fef3c7; }}
    p, li {{ line-height: 1.55; color: #e5e7eb; }}
  </style>
</head>
<body>
  <header>
    <div class="pill">{escape(episode.audience)}</div>
    <div class="pill">{escape(episode.aspect)} - {episode.width}x{episode.height}</div>
    <h1>{escape(episode.title)}</h1>
    <p>{escape(episode.logline)}</p>
    <p>Workspace: <code>{escape(str(root))}</code></p>
  </header>
  <main>
    <section class="grid">
      <div class="card">
        <h2>Create Story</h2>
        <p>Choose the audience and format, then copy the updated command. The current scene prompts below belong to <strong>{escape(episode.aspect)}</strong>; create a new workspace to switch formats cleanly.</p>
        <label>Audience</label>
        <select id="audience">
          <option value="kid" {"selected" if episode.audience == "kid" else ""}>Kid: 2-5 years, gentle motion in every scene</option>
          <option value="adult" {"selected" if episode.audience == "adult" else ""}>Adult: sci-fi, war, king/queen, mystery, adventure</option>
        </select>
        <label style="display:block; margin-top: 12px;">Format</label>
        <select id="aspect">
          <option value="shorts" {"selected" if episode.aspect == "shorts" else ""}>Shorts/Reels: 9:16</option>
          <option value="landscape" {"selected" if episode.aspect == "landscape" else ""}>Landscape YouTube: 16:9</option>
        </select>
        <div class="choice-row">
          <div class="choice"><strong>Kid rule</strong>Motion video for every scene: smiles, blinking, toys, clouds, sparkles.</div>
          <div class="choice"><strong>Adult rule</strong>2.5D for mood; motion video only for action, discovery or creative moments.</div>
        </div>
        <label>Optional idea</label>
        <input id="idea" placeholder="Example: a baby elephant learns to share toys">
        <p><strong>Ask Codex:</strong> "Create a story from this UI selection" or "Create a new story by yourself."</p>
        <label>Selected command</label>
        <textarea id="selected_command">{escape(current_command)}</textarea>
        <button onclick="copyText('selected_command')">Copy Selected Command</button>
        <br><br>
        <label>Kid command</label>
        <textarea id="kid_command">{escape(kid_command)}</textarea>
        <button onclick="copyText('kid_command')">Copy Kid Command</button>
        <br><br>
        <label>Adult command</label>
        <textarea id="adult_command">{escape(adult_command)}</textarea>
        <button onclick="copyText('adult_command')">Copy Adult Command</button>
        <br><br>
        <label>Last 3 backup stories</label>
        <select>{recent_options}</select>
      </div>
      <div class="card"><h2>Production Plan</h2><ul>{notes}</ul></div>
      <div class="card"><h2>Policy Notes</h2><ul>{safety}</ul></div>
    </section>
    <h2 style="margin-top: 30px;">Character References</h2>
    <section class="grid">{character_cards}</section>
    <h2 style="margin-top: 30px;">Scene Prompts</h2>
    <section class="grid">{cards}</section>
  </main>
  <script>
    function copyText(id) {{
      const el = document.getElementById(id);
      el.select();
      navigator.clipboard.writeText(el.value);
    }}
    function refreshSelectedCommand() {{
      const audience = document.getElementById('audience').value;
      const aspect = document.getElementById('aspect').value;
      const idea = document.getElementById('idea').value.trim();
      let command = `PYTHONPATH=src .venv/bin/python -m content_pipeline story-studio-create --audience ${{audience}} --aspect ${{aspect}} --date 2026-05-28`;
      if (idea) {{
        command += ` --idea "${{idea.replaceAll('"', '\\"')}}"`;
      }}
      document.getElementById('selected_command').value = command;
    }}
    document.getElementById('audience').addEventListener('change', refreshSelectedCommand);
    document.getElementById('aspect').addEventListener('change', refreshSelectedCommand);
    document.getElementById('idea').addEventListener('input', refreshSelectedCommand);
  </script>
</body>
</html>
"""


def _character_card(character: CharacterReference) -> str:
    prompt_id = f"character_{character.id}"
    return f"""<article class="card">
  <h3>{escape(character.name)}</h3>
  <p><strong>{escape(character.role)}</strong></p>
  <img class="character-img" src="../{escape(character.image_file)}" alt="{escape(character.name)} reference">
  <p>{escape(character.description)}</p>
  <label>Reference image prompt</label>
  <textarea id="{prompt_id}">{escape(character.reference_prompt)}</textarea>
  <button onclick="copyText('{prompt_id}')">Copy Character Prompt</button>
</article>"""


def _scene_card(scene: StoryScene, index: int) -> str:
    openart_id = f"openart_{index:02d}"
    meta_id = f"meta_{index:02d}"
    return f"""<article class="card scene">
  <div class="pill">Scene {index:02d}</div><div class="pill">{escape(scene.visual_mode)}</div>
  <h3>{escape(scene.title)}</h3>
  <p><strong>Narration:</strong> {escape(scene.narration)}</p>
  <p><strong>Save as:</strong> <code>{escape(scene.expected_clip_file)}</code></p>
  <label>OpenArt prompt</label>
  <textarea id="{openart_id}">{escape(scene.openart_prompt)}</textarea>
  <button onclick="copyText('{openart_id}')">Copy OpenArt Prompt</button>
  <br><br>
  <label>Meta AI prompt</label>
  <textarea id="{meta_id}">{escape(scene.meta_prompt)}</textarea>
  <button onclick="copyText('{meta_id}')">Copy Meta Prompt</button>
</article>"""


def _subtitle_srt(episode: StoryEpisode) -> str:
    lines: list[str] = []
    start = 0
    for index, scene in enumerate(episode.scenes, start=1):
        end = start + scene.duration_seconds
        lines.extend([str(index), f"{_timestamp(start)} --> {_timestamp(end)}", scene.narration, ""])
        start = end
    return "\n".join(lines)


def _character_svg(character: CharacterReference) -> str:
    color = "#60a5fa" if "elephant" in character.description.lower() else "#facc15"
    accent = "#f97316" if "bird" in character.description.lower() else "#22d3ee"
    title = escape(character.name)
    role = escape(character.role)
    description = escape(character.description)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="1280" viewBox="0 0 960 1280">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="#111827"/>
      <stop offset="1" stop-color="#312e81"/>
    </linearGradient>
  </defs>
  <rect width="960" height="1280" fill="url(#bg)"/>
  <rect x="64" y="64" width="832" height="1152" rx="44" fill="#f8fafc" opacity="0.96"/>
  <text x="96" y="142" fill="#111827" font-family="Arial, sans-serif" font-size="54" font-weight="700">{title}</text>
  <text x="96" y="196" fill="#475569" font-family="Arial, sans-serif" font-size="28">{role}</text>
  <circle cx="480" cy="430" r="190" fill="{color}"/>
  <circle cx="410" cy="394" r="26" fill="#111827"/>
  <circle cx="550" cy="394" r="26" fill="#111827"/>
  <circle cx="402" cy="386" r="8" fill="#ffffff"/>
  <circle cx="542" cy="386" r="8" fill="#ffffff"/>
  <path d="M405 505 Q480 565 555 505" fill="none" stroke="#111827" stroke-width="16" stroke-linecap="round"/>
  <rect x="310" y="635" width="340" height="310" rx="80" fill="{color}"/>
  <rect x="346" y="680" width="268" height="54" rx="27" fill="{accent}"/>
  <circle cx="315" cy="470" r="74" fill="{color}" opacity="0.92"/>
  <circle cx="645" cy="470" r="74" fill="{color}" opacity="0.92"/>
  <text x="96" y="1044" fill="#111827" font-family="Arial, sans-serif" font-size="26" font-weight="700">Consistency Notes</text>
  <foreignObject x="96" y="1070" width="768" height="110">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: Arial, sans-serif; font-size: 24px; line-height: 1.35; color: #334155;">{description}</div>
  </foreignObject>
</svg>
"""


def _timestamp(seconds: int) -> str:
    hours, remaining = divmod(seconds, 3600)
    minutes, seconds = divmod(remaining, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},000"


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _title_from_idea(idea: str, fallback: str) -> str:
    words = [word.strip(".,:;!?").capitalize() for word in idea.split()[:5]]
    return " ".join(words) if words else fallback


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")[:48]
