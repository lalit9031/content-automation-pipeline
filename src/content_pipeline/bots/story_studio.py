from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_default_policy
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

REFERENCE_VIDEO_EXTENSIONS = (".mp4", ".webm", ".mov")
REFERENCE_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg")
REFERENCE_MEDIA_EXTENSIONS = REFERENCE_VIDEO_EXTENSIONS + REFERENCE_IMAGE_EXTENSIONS
MAX_REFERENCE_UPLOAD_BYTES = 250 * 1024 * 1024


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
    references = root / "references" / "inbox"
    video = root / "video"
    ui = root / "ui"
    for directory in (inbox, references, video, ui):
        directory.mkdir(parents=True, exist_ok=True)
    (inbox / ".gitkeep").write_text("", encoding="utf-8")
    (references / ".gitkeep").write_text("", encoding="utf-8")

    paths = [
        _write_json(root / "episode.json", episode.as_dict()),
        _write_json(root / "characters" / "character_references.json", [asdict(character) for character in episode.characters]),
        _write_text(root / "story_script.md", _script_markdown(episode)),
        _write_json(root / "scene_prompts.json", _prompt_rows(episode)),
        _write_text(root / "clip_drop_guide.md", _clip_drop_guide(episode)),
        _write_text(root / "reference_media_guide.md", _reference_media_guide(episode)),
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


def save_reference_media_upload(workspace_dir: Path, character_id: str, original_filename: str, data: bytes) -> Path:
    workspace_dir = workspace_dir.resolve()
    episode = StoryEpisode.from_dict(json.loads((workspace_dir / "episode.json").read_text(encoding="utf-8")))
    character_ids = {character.id for character in episode.characters}
    if character_id not in character_ids:
        raise ValueError(f"Unknown character id: {character_id}")
    if not data:
        raise ValueError("Uploaded file is empty.")
    if len(data) > MAX_REFERENCE_UPLOAD_BYTES:
        raise ValueError("Uploaded file is larger than the 250 MB local limit.")
    extension = Path(original_filename).suffix.lower()
    if extension not in REFERENCE_MEDIA_EXTENSIONS:
        allowed = ", ".join(REFERENCE_MEDIA_EXTENSIONS)
        raise ValueError(f"Unsupported reference media type. Use one of: {allowed}")

    references = workspace_dir / "references" / "inbox"
    references.mkdir(parents=True, exist_ok=True)
    target = references / f"{character_id}_reference{extension}"
    for old_extension in REFERENCE_MEDIA_EXTENSIONS:
        old_path = references / f"{character_id}_reference{old_extension}"
        if old_path != target and old_path.exists():
            old_path.unlink()
    target.write_bytes(data)
    refresh_story_dashboard(workspace_dir)
    return target


def refresh_story_dashboard(workspace_dir: Path) -> Path:
    workspace_dir = workspace_dir.resolve()
    episode = StoryEpisode.from_dict(json.loads((workspace_dir / "episode.json").read_text(encoding="utf-8")))
    output_dir = _story_output_dir(workspace_dir)
    ui_path = workspace_dir / "ui" / "index.html"
    return _write_text(ui_path, _dashboard_html(episode, workspace_dir, recent_stories(output_dir)))


def serve_story_studio(workspace_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    workspace_dir = workspace_dir.resolve()
    if not (workspace_dir / "episode.json").exists():
        raise FileNotFoundError(f"Story Studio workspace not found: {workspace_dir}")
    refresh_story_dashboard(workspace_dir)

    class StoryStudioHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(workspace_dir), **kwargs)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path in {"/", ""}:
                self.send_response(302)
                self.send_header("Location", "/ui/index.html")
                self.end_headers()
                return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if self.path != "/upload-reference":
                self.send_error(404, "Unknown endpoint")
                return
            try:
                character_id, filename, payload = _parse_reference_upload(self)
                save_reference_media_upload(workspace_dir, character_id, filename, payload)
            except ValueError as exc:
                self.send_error(400, str(exc))
                return
            self.send_response(303)
            self.send_header("Location", "/ui/index.html")
            self.end_headers()

    server = ThreadingHTTPServer((host, port), StoryStudioHandler)
    print(f"Story Studio upload UI: http://{host}:{port}/ui/index.html")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _parse_reference_upload(handler: SimpleHTTPRequestHandler) -> tuple[str, str, bytes]:
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ValueError("Upload must use multipart/form-data.")
    content_length = int(handler.headers.get("Content-Length", "0"))
    if content_length <= 0:
        raise ValueError("Upload body is empty.")
    if content_length > MAX_REFERENCE_UPLOAD_BYTES + 1024 * 1024:
        raise ValueError("Upload request is too large.")
    body = handler.rfile.read(content_length)
    message = BytesParser(policy=email_default_policy).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8") + body
    )
    character_id = ""
    filename = ""
    payload = b""
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        if "form-data" not in disposition:
            continue
        name = part.get_param("name", header="content-disposition")
        if name == "character_id":
            character_id = part.get_content().strip()
        elif name == "media":
            filename = part.get_filename() or ""
            payload = part.get_payload(decode=True) or b""
    if not character_id:
        raise ValueError("Missing character id.")
    if not filename:
        raise ValueError("Missing media file.")
    return character_id, filename, payload


def _story_output_dir(workspace_dir: Path) -> Path:
    for parent in workspace_dir.parents:
        if parent.name == "story_studio":
            return parent.parent
    return workspace_dir.parent


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
            "momo_v1",
            "Momo the Bunny",
            "main character",
            "A round soft pink-and-white bunny with long floppy ears, big sparkly eyes, rosy cheeks, tiny pink nose, three whiskers per side, fluffy cotton-ball tail. Wears nothing except her natural fur. Always smiling with a gentle happy expression.",
            (
                "PROFESSIONAL CHARACTER REFERENCE SHEET for MOMO V1 — original 2-5 kids cartoon character.\n"
                "SPECIES: Bunny rabbit.\n"
                "BODY: Round soft preschool proportions, pear-shaped body, gentle curves.\n"
                "COLORS: Pale pink body (#f1c0c8), lighter pink belly, white inner ears and tail.\n"
                "FEATURES: Long floppy ears that droop gently, big round dark eyes with white catchlights, "
                "rosy circular cheek patches, small pink oval nose, cute whiskers (3 per side), small round tail.\n"
                "STYLE: Ultra-simple 3D cartoon, smooth rounded polygons, no sharp edges, no clothing, "
                "soft diffuse lighting, pastel nursery palette.\n"
                "POSES REQUIRED: Front view smiling, front view with arms up saying hello, side view hopping, "
                "close-up happy face.\n"
                "MOOD: Warm, gentle, curious, toddler-safe.\n"
                "ABSOLUTELY NO: Text, logos, watermarks, realistic fur, sharp edges, shadows on face, "
                "copyrighted elements, scary expressions."
            ),
            "characters/momo_v1_reference.svg",
        ),
        CharacterReference(
            "tinku_v1",
            "Tinku the Teddy",
            "main character",
            "A warm golden-brown teddy bear with round ears, a bright red bow tie at the neck, soft cream belly, big friendly eyes, a small oval black nose, and a gentle smile. Plump cuddly body, short rounded arms and legs.",
            (
                "PROFESSIONAL CHARACTER REFERENCE SHEET for TINKU V1 — original 2-5 kids cartoon character.\n"
                "SPECIES: Teddy bear.\n"
                "BODY: Plump cuddly pear shape, short rounded limbs, soft squishable appearance.\n"
                "COLORS: Golden-brown body (#8d6e63), cream belly and muzzle (#d7ccc8), bright red bow (#e53935).\n"
                "FEATURES: Round ears on top of head (inner ear lighter), large friendly dark eyes with white "
                "catchlights, oval black nose on cream snout, gentle curved smile, red bow tie at neck always tied.\n"
                "STYLE: Ultra-simple 3D cartoon, smooth rounded surfaces, soft warm lighting, toy-like finish.\n"
                "POSES REQUIRED: Front view waving, sitting pose hugging knees, side view waddling, "
                "close-up happy face with eyes closed smiling.\n"
                "MOOD: Friendly, cuddly, reassuring, patient.\n"
                "ABSOLUTELY NO: Text, logos, watermarks, realistic fur texture, sharp edges, "
                "copyrighted character imitation, scary or intense expressions."
            ),
            "characters/tinku_v1_reference.svg",
        ),
        CharacterReference(
            "pihu_v1",
            "Pihu the Little Cloud",
            "main character",
            "A fluffy white cloud shaped like a round cotton ball with a smiling face, bright blue eyes, rosy cheeks, a small pink smile. Wears a tiny rainbow-colored striped scarf. Has a few small raindrops that sometimes fall from her bottom edge. Soft dreamy appearance.",
            (
                "PROFESSIONAL CHARACTER REFERENCE SHEET for PIHU V1 — original 2-5 kids cartoon character.\n"
                "SPECIES: Personified cloud.\n"
                "BODY: Fluffy round cloud shape made of overlapping soft circles, cotton-ball texture (implied).\n"
                "COLORS: Pure white cloud body with soft light-blue inner shading, rainbow scarf (red-orange-green-blue stripes), "
                "bright blue eyes (#40c4ff), pink cheeks, teardrop-shaped raindrops (#40c4ff, semi-transparent).\n"
                "FEATURES: Two bright blue circular eyes with white catchlights, small pink oval mouth, "
                "circular rosy cheek patches, a thin rainbow-striped scarf that floats as if in a breeze, "
                "3-4 small teardrop raindrops dangling below (gently, not stormy).\n"
                "STYLE: Ultra-simple 3D cartoon, soft billowy surfaces, dreamy pastel lighting, gentle floating motion.\n"
                "POSES REQUIRED: Front view smiling, side view floating, happy rain pose with arms/cloud-puffs out, "
                "sleepy face closing eyes.\n"
                "MOOD: Dreamy, cheerful, gentle, magical.\n"
                "ABSOLUTELY NO: Text, logos, watermarks, dark storm clouds, lightning, realistic water, "
                "thunder, scary weather, sharp edges."
            ),
            "characters/pihu_v1_reference.svg",
        ),
        CharacterReference(
            "golu_v1",
            "Golu the Baby Elephant",
            "main character",
            "A round baby elephant with soft blue-gray skin, big gentle dark eyes with white sparkles, a long curved trunk, large flappy ears, a tiny yellow scarf tied at the neck, and a small red toy-car badge pinned on his left side. Sweet toddler-like expressions.",
            (
                "PROFESSIONAL CHARACTER REFERENCE SHEET for GOLU V1 — original 2-5 kids cartoon character.\n"
                "SPECIES: Baby elephant.\n"
                "BODY: Round pear-shaped toddler proportions, sturdy short legs, floppy appearance.\n"
                "COLORS: Soft blue-gray body (#90a4ae), lighter inner ears (#b0bec5), bright yellow scarf (#fdd835), "
                "tiny red toy-car badge (#e53935) with yellow wheels.\n"
                "FEATURES: Large flappy ears extending sideways from head (lighter inside), long gently curved trunk, "
                "big dark circular eyes with white catchlights, gentle curved smile, short sturdy legs, "
                "yellow knitted scarf that hangs loosely, tiny red car badge (circle with wheels) on left chest.\n"
                "STYLE: Ultra-simple 3D cartoon, smooth rounded surfaces, soft warm nursery lighting, "
                "gentle and huggable proportions.\n"
                "POSES REQUIRED: Front view smiling with trunk up, side view walking, sitting pose with toys, "
                "close-up happy squinting eyes smile.\n"
                "MOOD: Sweet, curious, gentle, slightly shy but friendly.\n"
                "ABSOLUTELY NO: Text, logos, watermarks, realistic skin texture, tusks, "
                "sharp edges, scary expressions, copyrighted character imitation."
            ),
            "characters/golu_v1_reference.svg",
        ),
        CharacterReference(
            "mimi_v1",
            "Mimi the Bird",
            "friend",
            "A tiny round yellow bird with bright orange feet, a small teal bow on top of her head, big friendly dark eyes, a tiny orange triangular beak, small rounded wings, and short tail feathers. Very small — about half the size of the other characters.",
            (
                "PROFESSIONAL CHARACTER REFERENCE SHEET for MIMI V1 — original 2-5 kids cartoon character.\n"
                "SPECIES: Small songbird.\n"
                "BODY: Tiny round ball shape — approximately half the size of other characters, "
                "chubby bird proportions, no visible neck.\n"
                "COLORS: Bright warm yellow body (#fdd835), lighter yellow belly (#fff176), "
                "bright orange beak and feet (#ff6f00), teal bow (#26c6da) with darker center (#00acc1).\n"
                "FEATURES: Two small dark circular eyes with white catchlights, small triangular orange beak, "
                "small rounded wings on sides, short tail feathers at back, teal bow tied on top of head, "
                "thin orange stick legs with three-toed feet, circular rosy cheek patches.\n"
                "STYLE: Ultra-simple 3D cartoon, tiny and round, bouncy motion, warm sunny palette.\n"
                "POSES REQUIRED: Front view chirping, side view flying with wings out, hopping pose (one foot up), "
                "close-up happy face.\n"
                "MOOD: Playful, curious, cheerful, bouncy.\n"
                "ABSOLUTELY NO: Text, logos, watermarks, realistic feathers, sharp beak, "
                "copyrighted character imitation, scary expressions, sharp edges."
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
            "main character — human space explorer",
            "A determined adult space explorer in her mid-30s with sharp angular features, short practical dark hair tucked under a matte-white helmet, warm brown eyes visible through the amber-tinted visor, a focused but thoughtful expression. She wears a matte-white EVA suit with cobalt-blue trim stripes along the arms and legs, a triangular red-and-gold mission patch on the left shoulder (symbol: a seven-pointed star above crossed orbits), a compact tactical shoulder light, a grey utility belt with two silver pouches, and reinforced knee pads. Her gloved hands have articulated fingers. The suit surface shows subtle scuff marks and frost crystals at the collar, implying recent EVA activity.",
            (
                "PROFESSIONAL CHARACTER REFERENCE SHEET for COMMANDER IRA V1 — original adult sci-fi character.\n"
                "SPECIES: Human (female).\n"
                "AGE: Mid-30s, experienced deep-space mission commander.\n"
                "BODY: Lean athletic build, 170 cm, sharp jawline, straight posture, practical confident stance.\n"
                "SUIT COLORS: Matte white body (#e0e0e0), cobalt blue trim (#1a237e), grey joints (#78909c),\n"
                "amber visor (#ff8f00, semi-reflective gradient), red-and-gold shoulder patch (#d32f2f / #fdd835).\n"
                "HELMET: Full EVA helmet, circular matte-white shell, amber-tinted curved visor that hides the upper face \n"
                "in reflections but reveals warm brown eyes from certain angles, breathing tube on right jaw, \n"
                "small white LED light module on left temple.\n"
                "DETAILS: Compact shoulder light (grey cylinder with yellow lens), grey canvas utility belt with \n"
                "two silver pouches, reinforced grey knee pads, articulated grey glove fingers, \n"
                "triangular mission patch on left deltoid (seven-pointed star over crossed orbits, red/gold on navy).\n"
                "WEATHERING: Subtle scuff marks on knees and elbows, frost crystals at collar seal, \n"
                "faint blue tint on visor edges from ice residue.\n"
                "STYLE: Cinematic semi-realistic 3D rendering, dramatic lighting (key light from upper right), \n"
                "medium surface detail, dark-space background with faint star field.\n"
                "POSES REQUIRED: Front full-body standing (confident stance, helmet on), \n"
                "three-quarter body (hand on hip, looking right), helmet close-up (amber reflection, eyes visible), \n"
                "crouched examination pose (one knee down, reaching forward).\n"
                "MOOD: Determined, weary, curious, professional but deeply tired.\n"
                "ABSOLUTELY NO: Text, logos, watermarks, realistic blood, copyrighted franchise elements, \n"
                "excessive gore, stylized anime proportions, weapon in hand."
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


def _reference_media_guide(episode: StoryEpisode) -> str:
    lines = [
        "# Character Reference Media Guide",
        "",
        "Use Gemini/OpenArt to create one strong reference image per character first.",
        "A clean PNG/JPG character image is the best default for consistent faces, colors and body shape.",
        "Use MP4/MOV/WebM only as an optional motion reference when a character action is hard to describe.",
        "The dashboard displays these files when they are placed in `references/inbox/`.",
        "",
        "Preferred filenames:",
        "",
    ]
    for character in episode.characters:
        lines.extend(
            [
                f"- `{character.id}_reference.png` or `{character.id}_reference.jpg` - recommended character look reference",
                f"- `{character.id}_reference.mp4` - optional motion reference",
            ]
        )
    lines.extend(
        [
            "",
            "The old generated SVG sheets are draft prompts only. For production, use a clean Gemini/OpenArt PNG/JPG character reference.",
            "",
        ]
    )
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
    character_cards = "\n".join(_character_card(character, root) for character in episode.characters)
    notes = "\n".join(f"<li>{escape(note)}</li>" for note in episode.production_notes)
    safety = "\n".join(f"<li>{escape(rule)}</li>" for rule in episode.safety_rules)
    status_html = _production_status_html(episode, root)
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
    is_kid = episode.audience == "kid"
    if is_kid:
        return _kid_dashboard_html(
            episode, root, recent, recent_options, cards, character_cards,
            notes, safety, status_html, current_command, kid_command, adult_command,
        )
    return _adult_dashboard_html(
        episode, root, recent, recent_options, cards, character_cards,
        notes, safety, status_html, current_command, kid_command, adult_command,
    )


def _production_status_html(episode: StoryEpisode, root: Path) -> str:
    reference_ready = sum(1 for character in episode.characters if _reference_media_path(character, root))
    clips_ready = sum(1 for scene in episode.scenes if (root / "clips" / "inbox" / scene.expected_clip_file).exists())
    rows = [
        _status_row("Story/script", (root / "story_script.md").exists(), "Script ready"),
        _status_row("Scene prompts", (root / "scene_prompts.json").exists(), "Prompts ready"),
        _status_row(
            "Character references",
            reference_ready == len(episode.characters),
            f"{reference_ready}/{len(episode.characters)} reference media files added",
        ),
        _status_row(
            "Manual/Gemini clips",
            clips_ready == len(episode.scenes),
            f"{clips_ready}/{len(episode.scenes)} scene clips in clips/inbox",
        ),
        _status_row("Final assembly", (root / "video" / "assembled_review.mp4").exists(), "Review MP4 exported"),
    ]
    budget = _budget_summary_html(root)
    fallback = (
        "Automation plan: use Gemini/Veo API while quota is available. "
        "If quota is exhausted, create the missing clips manually in Gemini/OpenArt using the scene prompts below, "
        "then save them with the expected filenames."
    )
    return f"""<p style="margin-bottom: 10px;">{escape(fallback)}</p>
<ul style="list-style: none; padding-left: 0;">{''.join(rows)}</ul>
{budget}"""


def _status_row(label: str, done: bool, detail: str) -> str:
    marker = "Done" if done else "Needs manual"
    color = "#059669" if done else "#d97706"
    return (
        f'<li style="margin-bottom: 8px;"><strong>{escape(label)}:</strong> '
        f'<span style="color: {color}; font-weight: 700;">{marker}</span><br>'
        f'<span style="font-size: 12px;">{escape(detail)}</span></li>'
    )


def _budget_summary_html(root: Path) -> str:
    path = root / "gemini_budget_report.json"
    if not path.exists():
        return (
            '<hr><p style="font-size: 12px;"><strong>Budget Agent:</strong> Not run yet. '
            'Run <code>story-studio-budget-report</code> to estimate Gemini/Veo cost and quota strategy.</p>'
        )
    report = json.loads(path.read_text(encoding="utf-8"))
    advice = "".join(f"<li>{escape(item)}</li>" for item in report.get("advice", []))
    return f"""<hr>
<p style="font-size: 12px;"><strong>Budget Agent:</strong> {report.get("completed_scenes", 0)}/{report.get("total_scenes", 0)} clips ready, {report.get("pending_scenes", 0)} pending.</p>
<p style="font-size: 12px;">Recommended auto today: {len(report.get("recommended_auto_today", []))} clips / approx ${report.get("recommended_auto_today_cost_usd", 0)}. Remaining estimate: ${report.get("estimated_remaining_cost_usd", 0)}.</p>
<ul>{advice}</ul>"""


def _kid_dashboard_html(
    episode: StoryEpisode, root: Path, recent: list[dict[str, str]],
    recent_options: str, cards: str, character_cards: str,
    notes: str, safety: str, status_html: str, current_command: str,
    kid_command: str, adult_command: str,
) -> str:
    """Professional production dashboard for kids content — clean, modern, SaaS-style."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(episode.title)} — Story Studio</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; background: #f1f5f9; color: #1e293b; line-height: 1.5; }}
    .app {{ display: flex; min-height: 100vh; }}
    /* Sidebar */
    .sidebar {{ width: 240px; flex-shrink: 0; background: #0f172a; color: #e2e8f0; padding: 0; }}
    .sidebar-head {{ padding: 20px 20px 12px; border-bottom: 1px solid #1e293b; }}
    .sidebar-head h1 {{ font-size: 15px; font-weight: 700; color: #f1f5f9; letter-spacing: -0.3px; }}
    .sidebar-head p {{ font-size: 11px; color: #64748b; margin-top: 2px; }}
    .sidebar-nav {{ padding: 12px 0; }}
    .sidebar-nav a {{ display: flex; align-items: center; gap: 10px; padding: 8px 20px; font-size: 13px; color: #94a3b8; text-decoration: none; border-left: 3px solid transparent; transition: all 0.12s; }}
    .sidebar-nav a:hover {{ background: #1e293b; color: #e2e8f0; }}
    .sidebar-nav a.active {{ background: #1e293b; color: #60a5fa; border-left-color: #60a5fa; font-weight: 600; }}
    /* Main */
    .main {{ flex: 1; min-width: 0; }}
    /* Top bar */
    .topbar {{ display: flex; align-items: center; justify-content: space-between; padding: 16px 32px; background: #ffffff; border-bottom: 1px solid #e2e8f0; }}
    .topbar-left {{ display: flex; align-items: center; gap: 12px; }}
    .topbar-left h2 {{ font-size: 18px; font-weight: 600; color: #0f172a; }}
    .badge {{ display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 600; }}
    .badge-kid {{ background: #fce7f3; color: #be185d; }}
    .badge-blue {{ background: #dbeafe; color: #1d4ed8; }}
    .badge-green {{ background: #d1fae5; color: #059669; }}
    .badge-amber {{ background: #fef3c7; color: #d97706; }}
    .topbar-right {{ display: flex; align-items: center; gap: 10px; font-size: 13px; color: #64748b; }}
    .topbar-right code {{ font-size: 12px; background: #f1f5f9; padding: 2px 8px; border-radius: 4px; color: #475569; }}
    /* Content */
    .content {{ padding: 28px 32px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }}
    .grid-wide {{ grid-template-columns: 1fr 1fr; }}
    .card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); transition: box-shadow 0.18s; }}
    .card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.06); }}
    .scene {{ border-left: 4px solid #f59e0b; }}
    .char-card {{ border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; background: #ffffff; transition: box-shadow 0.18s; }}
    .char-card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.06); }}
    .card h3 {{ font-size: 15px; font-weight: 600; color: #0f172a; margin-bottom: 6px; }}
    .card p, .card li {{ font-size: 13px; color: #475569; line-height: 1.55; }}
    .card ul {{ padding-left: 16px; }}
    .card li {{ margin-bottom: 4px; }}
    .section-title {{ font-size: 16px; font-weight: 600; color: #0f172a; margin: 28px 0 16px; display: flex; align-items: center; gap: 8px; }}
    .section-title .count {{ font-size: 12px; font-weight: 500; color: #64748b; background: #f1f5f9; padding: 2px 10px; border-radius: 999px; }}
    .character-img {{ width: 100%; border-radius: 8px; background: #f8fafc; border: 1px solid #e2e8f0; transition: transform 0.2s; }}
    .character-img:hover {{ transform: scale(1.01); }}
    textarea, select, input {{ width: 100%; box-sizing: border-box; border-radius: 8px; border: 1px solid #cbd5e1; padding: 10px 12px; background: #ffffff; color: #1e293b; font-family: 'SF Mono', 'Consolas', 'Monaco', monospace; font-size: 13px; transition: border-color 0.15s; }}
    textarea:focus, select:focus, input:focus {{ outline: none; border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }}
    textarea {{ min-height: 120px; }}
    select {{ font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; }}
    label {{ display: block; margin: 12px 0 4px; font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}
    button {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #ffffff; border: 0; border-radius: 8px; padding: 9px 16px; font-weight: 600; cursor: pointer; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; font-size: 13px; transition: all 0.12s; box-shadow: 0 2px 8px rgba(99,102,241,0.2); }}
    button:hover {{ transform: translateY(-1px); box-shadow: 0 4px 14px rgba(99,102,241,0.3); }}
    button:active {{ transform: translateY(0); }}
    .btn-sm {{ padding: 6px 12px; font-size: 12px; }}
    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; color: #475569; font-size: 12px; }}
    .pill {{ display: inline-block; margin: 2px 4px 2px 0; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; }}
    .pill-blue {{ background: #dbeafe; color: #1d4ed8; }}
    .pill-green {{ background: #d1fae5; color: #059669; }}
    .pill-amber {{ background: #fef3c7; color: #d97706; }}
    .pill-pink {{ background: #fce7f3; color: #be185d; }}
    .choice-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 8px 0 12px; }}
    .choice {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; background: #f8fafc; font-size: 12px; color: #475569; }}
    .choice strong {{ display: block; margin-bottom: 2px; color: #0f172a; font-size: 12px; }}
    .char-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
    .char-header .emoji {{ font-size: 28px; }}
    .char-header .info {{ flex: 1; }}
    .char-header .info h3 {{ margin: 0 0 2px; font-size: 15px; }}
    .char-header .info .role {{ font-size: 12px; color: #64748b; }}
    details summary {{ cursor: pointer; font-size: 12px; font-weight: 600; color: #6366f1; padding: 4px 0; }}
    details summary:hover {{ color: #4f46e5; }}
    .mb-4 {{ margin-bottom: 4px; }}
    .mt-8 {{ margin-top: 8px; }}
    .flex {{ display: flex; }} .gap-8 {{ gap: 8px; }} .items-center {{ align-items: center; }}
    .char-summary {{ cursor: pointer; color: #7b1fa2; font-weight: 700; font-size: 14px; }}
    .char-summary:hover {{ color: #4a148c; }}
    hr {{ border: 0; border-top: 1px solid #e2e8f0; margin: 14px 0; }}
    @media (max-width: 800px) {{ .app {{ flex-direction: column; }} .sidebar {{ width: 100%; }} .grid-wide {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="sidebar-head">
        <h1>Story Studio</h1>
        <p>Content Pipeline v1</p>
      </div>
      <nav class="sidebar-nav">
        <a href="#" class="active">&#9679; Dashboard</a>
        <a href="#">&#9679; Episodes</a>
        <a href="#">&#9679; Characters</a>
        <a href="#">&#9679; Assets</a>
        <a href="#">&#9679; Settings</a>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="topbar-left">
          <span class="badge badge-kid">{escape(episode.audience)}</span>
          <span class="badge badge-blue">{escape(episode.aspect)}</span>
          <span class="badge badge-green">{episode.target_duration_seconds}s</span>
          <h2>{escape(episode.title)}</h2>
        </div>
        <div class="topbar-right">
          <span>{escape(str(root))}</span>
        </div>
      </header>
      <div class="content">
        <p style="font-size: 14px; color: #64748b; margin-bottom: 20px;">{escape(episode.logline)}</p>
        <section class="grid grid-wide" style="margin-bottom: 8px;">
          <div class="card">
            <h3>Create Story</h3>
            <p style="margin-bottom: 12px;">Choose audience and format, then copy the command.</p>
            <label>Audience</label>
            <select id="audience">
              <option value="kid" {"selected" if episode.audience == "kid" else ""}>Kid: 2–5 years, gentle motion</option>
              <option value="adult" {"selected" if episode.audience == "adult" else ""}>Adult: sci-fi, war, mystery</option>
            </select>
            <label style="margin-top: 10px;">Format</label>
            <select id="aspect">
              <option value="shorts" {"selected" if episode.aspect == "shorts" else ""}>Shorts / Reels — 9:16</option>
              <option value="landscape" {"selected" if episode.aspect == "landscape" else ""}>Landscape YouTube — 16:9</option>
            </select>
            <div class="choice-row">
              <div class="choice"><strong>Kid rule</strong>Motion in every scene: smiles, toys, sparkles</div>
              <div class="choice"><strong>Adult rule</strong>2.5D for mood; motion for action scenes</div>
            </div>
            <label>Optional idea</label>
            <input id="idea" placeholder="Type a story idea…" style="font-family: system-ui; font-size: 13px;">
            <div class="flex items-center gap-8" style="margin-top: 8px;">
              <label style="margin: 0; white-space: nowrap;">Command</label>
              <textarea id="selected_command" style="min-height: 44px; font-size: 12px;">{escape(current_command)}</textarea>
              <button onclick="copyText('selected_command')" style="white-space: nowrap;">Copy</button>
            </div>
            <hr>
            <div class="flex items-center gap-8">
              <label style="margin: 0; white-space: nowrap; flex-shrink: 0; width: 60px;">Kid</label>
              <textarea id="kid_command" style="min-height: 36px; font-size: 11px;">{escape(kid_command)}</textarea>
              <button onclick="copyText('kid_command')" class="btn-sm">Copy</button>
            </div>
            <div class="flex items-center gap-8" style="margin-top: 4px;">
              <label style="margin: 0; white-space: nowrap; flex-shrink: 0; width: 60px;">Adult</label>
              <textarea id="adult_command" style="min-height: 36px; font-size: 11px;">{escape(adult_command)}</textarea>
              <button onclick="copyText('adult_command')" class="btn-sm">Copy</button>
            </div>
            <hr>
            <label>Recent stories</label>
            <select>{recent_options}</select>
          </div>
          <div class="card">
            <h3>Production Status</h3>
            {status_html}
          </div>
          <div class="card">
            <h3>Production Plan</h3>
            <ul>{notes}</ul>
            <h3 style="margin-top: 16px;">Safety Rules</h3>
            <ul>{safety}</ul>
          </div>
        </section>
        <div class="section-title">
          Character References <span class="count">{len(episode.characters)}</span>
        </div>
        <section class="grid" id="character-gallery">{character_cards}</section>
        <div class="section-title">
          Scene Prompts <span class="count">{len(episode.scenes)}</span>
        </div>
        <section class="grid" id="scene-gallery">{cards}</section>
      </div>
    </div>
  </div>
  <script>
    function copyText(id) {{
      const el = document.getElementById(id);
      el.select();
      navigator.clipboard.writeText(el.value);
      const btn = el.nextElementSibling;
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = orig, 1000);
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


def _adult_dashboard_html(
    episode: StoryEpisode, root: Path, recent: list[dict[str, str]],
    recent_options: str, cards: str, character_cards: str,
    notes: str, safety: str, status_html: str, current_command: str,
    kid_command: str, adult_command: str,
) -> str:
    """Professional production dashboard for adult content — dark theme, same layout as kid dashboard."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(episode.title)} — Story Studio</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; background: #0b1120; color: #e2e8f0; line-height: 1.5; }}
    .app {{ display: flex; min-height: 100vh; }}
    /* Sidebar */
    .sidebar {{ width: 240px; flex-shrink: 0; background: #060b17; color: #e2e8f0; padding: 0; border-right: 1px solid #1e293b; }}
    .sidebar-head {{ padding: 20px 20px 12px; border-bottom: 1px solid #1e293b; }}
    .sidebar-head h1 {{ font-size: 15px; font-weight: 700; color: #f1f5f9; letter-spacing: -0.3px; }}
    .sidebar-head p {{ font-size: 11px; color: #475569; margin-top: 2px; }}
    .sidebar-nav {{ padding: 12px 0; }}
    .sidebar-nav a {{ display: flex; align-items: center; gap: 10px; padding: 8px 20px; font-size: 13px; color: #64748b; text-decoration: none; border-left: 3px solid transparent; transition: all 0.12s; }}
    .sidebar-nav a:hover {{ background: #0f172a; color: #e2e8f0; }}
    .sidebar-nav a.active {{ background: #0f172a; color: #818cf8; border-left-color: #818cf8; font-weight: 600; }}
    /* Main */
    .main {{ flex: 1; min-width: 0; }}
    /* Top bar */
    .topbar {{ display: flex; align-items: center; justify-content: space-between; padding: 16px 32px; background: #0f172a; border-bottom: 1px solid #1e293b; }}
    .topbar-left {{ display: flex; align-items: center; gap: 12px; }}
    .topbar-left h2 {{ font-size: 18px; font-weight: 600; color: #f1f5f9; }}
    .badge {{ display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; }}
    .badge-adult {{ background: rgba(139,92,246,0.15); color: #c4b5fd; border: 1px solid rgba(139,92,246,0.2); }}
    .badge-blue {{ background: rgba(59,130,246,0.15); color: #93c5fd; border: 1px solid rgba(59,130,246,0.2); }}
    .badge-green {{ background: rgba(34,197,94,0.15); color: #86efac; border: 1px solid rgba(34,197,94,0.2); }}
    .topbar-right {{ display: flex; align-items: center; gap: 10px; font-size: 13px; color: #64748b; }}
    .topbar-right code {{ font-size: 12px; background: #1e293b; padding: 2px 8px; border-radius: 4px; color: #94a3b8; }}
    /* Content */
    .content {{ padding: 28px 32px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; }}
    .grid-wide {{ grid-template-columns: 1fr 1fr; }}
    .card {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.2); transition: border-color 0.18s; }}
    .card:hover {{ border-color: #334155; }}
    .scene {{ border-left: 4px solid #f59e0b; }}
    .char-card {{ border: 1px solid #1e293b; border-radius: 12px; padding: 20px; background: #0f172a; transition: border-color 0.18s; }}
    .char-card:hover {{ border-color: #334155; }}
    .card h3 {{ font-size: 15px; font-weight: 600; color: #f1f5f9; margin-bottom: 6px; }}
    .card p, .card li {{ font-size: 13px; color: #94a3b8; line-height: 1.55; }}
    .card ul {{ padding-left: 16px; }}
    .card li {{ margin-bottom: 4px; }}
    .section-title {{ font-size: 16px; font-weight: 600; color: #f1f5f9; margin: 28px 0 16px; display: flex; align-items: center; gap: 8px; }}
    .section-title .count {{ font-size: 12px; font-weight: 500; color: #94a3b8; background: #1e293b; padding: 2px 10px; border-radius: 999px; }}
    .character-img {{ width: 100%; border-radius: 8px; background: #060b17; border: 1px solid #1e293b; transition: transform 0.2s; }}
    .character-img:hover {{ transform: scale(1.01); }}
    textarea, select, input {{ width: 100%; box-sizing: border-box; border-radius: 8px; border: 1px solid #334155; padding: 10px 12px; background: #060b17; color: #e2e8f0; font-family: 'SF Mono', 'Consolas', 'Monaco', monospace; font-size: 13px; transition: border-color 0.15s; }}
    textarea:focus, select:focus, input:focus {{ outline: none; border-color: #818cf8; box-shadow: 0 0 0 3px rgba(129,140,248,0.1); }}
    textarea {{ min-height: 120px; }}
    select {{ font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; }}
    label {{ display: block; margin: 12px 0 4px; font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}
    button {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #ffffff; border: 0; border-radius: 8px; padding: 9px 16px; font-weight: 600; cursor: pointer; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; font-size: 13px; transition: all 0.12s; box-shadow: 0 2px 8px rgba(99,102,241,0.2); }}
    button:hover {{ transform: translateY(-1px); box-shadow: 0 4px 14px rgba(99,102,241,0.3); }}
    button:active {{ transform: translateY(0); }}
    .btn-sm {{ padding: 6px 12px; font-size: 12px; }}
    code {{ background: #1e293b; padding: 2px 6px; border-radius: 4px; color: #94a3b8; font-size: 12px; }}
    .pill {{ display: inline-block; margin: 2px 4px 2px 0; padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 600; }}
    .pill-blue {{ background: rgba(59,130,246,0.15); color: #93c5fd; border: 1px solid rgba(59,130,246,0.2); }}
    .pill-green {{ background: rgba(34,197,94,0.15); color: #86efac; border: 1px solid rgba(34,197,94,0.2); }}
    .pill-amber {{ background: rgba(245,158,11,0.15); color: #fcd34d; border: 1px solid rgba(245,158,11,0.2); }}
    .pill-purple {{ background: rgba(139,92,246,0.15); color: #c4b5fd; border: 1px solid rgba(139,92,246,0.2); }}
    .choice-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 8px 0 12px; }}
    .choice {{ border: 1px solid #334155; border-radius: 8px; padding: 10px; background: #060b17; font-size: 12px; color: #94a3b8; }}
    .choice strong {{ display: block; margin-bottom: 2px; color: #e2e8f0; font-size: 12px; }}
    .char-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
    .char-header .emoji {{ font-size: 28px; }}
    .char-header .info {{ flex: 1; }}
    .char-header .info h3 {{ margin: 0 0 2px; font-size: 15px; }}
    .char-header .info .role {{ font-size: 12px; color: #64748b; }}
    details summary {{ cursor: pointer; font-size: 12px; font-weight: 600; color: #818cf8; padding: 4px 0; }}
    details summary:hover {{ color: #a5b4fc; }}
    .mb-4 {{ margin-bottom: 4px; }}
    .mt-8 {{ margin-top: 8px; }}
    .flex {{ display: flex; }} .gap-8 {{ gap: 8px; }} .items-center {{ align-items: center; }}
    .char-summary {{ cursor: pointer; color: #a78bfa; font-weight: 700; font-size: 14px; }}
    .char-summary:hover {{ color: #c4b5fd; }}
    hr {{ border: 0; border-top: 1px solid #1e293b; margin: 14px 0; }}
    @media (max-width: 800px) {{ .app {{ flex-direction: column; }} .sidebar {{ width: 100%; }} .grid-wide {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="sidebar-head">
        <h1>Story Studio</h1>
        <p>Content Pipeline v1</p>
      </div>
      <nav class="sidebar-nav">
        <a href="#" class="active">&#9679; Dashboard</a>
        <a href="#">&#9679; Episodes</a>
        <a href="#">&#9679; Characters</a>
        <a href="#">&#9679; Assets</a>
        <a href="#">&#9679; Settings</a>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <div class="topbar-left">
          <span class="badge badge-adult">{escape(episode.audience)}</span>
          <span class="badge badge-blue">{escape(episode.aspect)}</span>
          <span class="badge badge-green">{episode.target_duration_seconds}s</span>
          <h2>{escape(episode.title)}</h2>
        </div>
        <div class="topbar-right">
          <span>{escape(str(root))}</span>
        </div>
      </header>
      <div class="content">
        <p style="font-size: 14px; color: #64748b; margin-bottom: 20px;">{escape(episode.logline)}</p>
        <section class="grid grid-wide" style="margin-bottom: 8px;">
          <div class="card">
            <h3>Create Story</h3>
            <p style="margin-bottom: 12px;">Choose audience and format, then copy the command.</p>
            <label>Audience</label>
            <select id="audience">
              <option value="kid" {"selected" if episode.audience == "kid" else ""}>Kid: 2–5 years, gentle motion</option>
              <option value="adult" {"selected" if episode.audience == "adult" else ""}>Adult: sci-fi, war, mystery</option>
            </select>
            <label style="margin-top: 10px;">Format</label>
            <select id="aspect">
              <option value="shorts" {"selected" if episode.aspect == "shorts" else ""}>Shorts / Reels — 9:16</option>
              <option value="landscape" {"selected" if episode.aspect == "landscape" else ""}>Landscape YouTube — 16:9</option>
            </select>
            <div class="choice-row">
              <div class="choice"><strong>Kid rule</strong>Motion in every scene: smiles, toys, sparkles</div>
              <div class="choice"><strong>Adult rule</strong>2.5D for mood; motion for action scenes</div>
            </div>
            <label>Optional idea</label>
            <input id="idea" placeholder="Type a story idea…" style="font-family: system-ui; font-size: 13px;">
            <div class="flex items-center gap-8" style="margin-top: 8px;">
              <label style="margin: 0; white-space: nowrap;">Command</label>
              <textarea id="selected_command" style="min-height: 44px; font-size: 12px;">{escape(current_command)}</textarea>
              <button onclick="copyText('selected_command')" style="white-space: nowrap;">Copy</button>
            </div>
            <hr>
            <div class="flex items-center gap-8">
              <label style="margin: 0; white-space: nowrap; flex-shrink: 0; width: 60px;">Kid</label>
              <textarea id="kid_command" style="min-height: 36px; font-size: 11px;">{escape(kid_command)}</textarea>
              <button onclick="copyText('kid_command')" class="btn-sm">Copy</button>
            </div>
            <div class="flex items-center gap-8" style="margin-top: 4px;">
              <label style="margin: 0; white-space: nowrap; flex-shrink: 0; width: 60px;">Adult</label>
              <textarea id="adult_command" style="min-height: 36px; font-size: 11px;">{escape(adult_command)}</textarea>
              <button onclick="copyText('adult_command')" class="btn-sm">Copy</button>
            </div>
            <hr>
            <label>Recent stories</label>
            <select>{recent_options}</select>
          </div>
          <div class="card">
            <h3>Production Status</h3>
            {status_html}
          </div>
          <div class="card">
            <h3>Production Plan</h3>
            <ul>{notes}</ul>
            <h3 style="margin-top: 16px;">Safety Rules</h3>
            <ul>{safety}</ul>
          </div>
        </section>
        <div class="section-title">
          Character References <span class="count">{len(episode.characters)}</span>
        </div>
        <section class="grid" id="character-gallery">{character_cards}</section>
        <div class="section-title">
          Scene Prompts <span class="count">{len(episode.scenes)}</span>
        </div>
        <section class="grid" id="scene-gallery">{cards}</section>
      </div>
    </div>
  </div>
  <script>
    function copyText(id) {{
      const el = document.getElementById(id);
      el.select();
      navigator.clipboard.writeText(el.value);
      const btn = el.nextElementSibling;
      const orig = btn.textContent;
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = orig, 1000);
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


def _character_card(character: CharacterReference, root: Path) -> str:
    prompt_id = f"character_{character.id}"
    emoji = _char_emoji(character.id)
    media_html = _reference_media_html(character, root)
    upload_html = _reference_upload_form(character)
    return f"""<article class="card char-card">
  <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
    <span style="font-size: 36px;">{emoji}</span>
    <div>
      <h3 style="margin: 0 0 2px 0;">{escape(character.name)}</h3>
      <span style="font-size: 13px; color: #888; font-weight: 600;">{escape(character.role)}</span>
    </div>
  </div>
  {media_html}
  <p style="font-size: 14px; margin: 10px 0;">{escape(character.description)}</p>
  <p style="font-size: 12px; color: #64748b;"><strong>Reference slot:</strong> upload a clean PNG/JPG first for character consistency. Video is optional for motion style.</p>
  {upload_html}
  <details>
    <summary class="char-summary">Reference Prompt</summary>
    <textarea id="{prompt_id}" style="margin-top: 8px;">{escape(character.reference_prompt)}</textarea>
    <button onclick="copyText('{prompt_id}')" style="margin-top: 6px;"> Copy Prompt</button>
  </details>
</article>"""


def _reference_upload_form(character: CharacterReference) -> str:
    return f"""<form method="post" action="/upload-reference" enctype="multipart/form-data" style="margin: 10px 0; padding: 10px; border: 1px dashed #cbd5e1; border-radius: 12px; background: #f8fafc;">
    <input type="hidden" name="character_id" value="{escape(character.id)}">
    <label style="display: block; font-size: 12px; font-weight: 700; margin-bottom: 6px;">Upload character reference for {escape(character.name)}</label>
    <input type="file" name="media" accept="image/png,image/jpeg,image/svg+xml,video/mp4,video/webm,video/quicktime" required style="width: 100%; font-size: 12px;">
    <button type="submit" style="margin-top: 8px;">Upload Reference</button>
    <p style="font-size: 11px; color: #64748b; margin: 8px 0 0;">Recommended: PNG/JPG image. Optional: MP4/MOV/WebM motion reference. File is auto-renamed to <code>{escape(character.id)}_reference.ext</code>.</p>
  </form>"""


def _reference_media_html(character: CharacterReference, root: Path) -> str:
    media_path = _reference_media_path(character, root)
    if media_path:
        relative = media_path.relative_to(root)
        if media_path.suffix.lower() in REFERENCE_VIDEO_EXTENSIONS:
            return (
                f'<video class="character-img" src="../{escape(str(relative))}" '
                'controls muted loop playsinline></video>'
            )
        return f'<img class="character-img" src="../{escape(str(relative))}" alt="{escape(character.name)} reference">'
    return (
        '<div class="character-img" style="min-height: 180px; display: grid; place-items: center; '
        'padding: 18px; text-align: center; color: #64748b;">'
        f'<div><strong>{escape(character.name)} reference media not added yet</strong><br>'
        f'<span>Upload {escape(character.id)}_reference.png or .jpg first; video is optional.</span></div></div>'
    )


def _reference_media_path(character: CharacterReference, root: Path) -> Path | None:
    for extension in REFERENCE_VIDEO_EXTENSIONS:
        relative = Path("references") / "inbox" / f"{character.id}_reference{extension}"
        if (root / relative).exists():
            return root / relative
    for extension in REFERENCE_IMAGE_EXTENSIONS:
        relative = Path("references") / "inbox" / f"{character.id}_reference{extension}"
        if (root / relative).exists():
            return root / relative
    return None


def _char_emoji(char_id: str) -> str:
    """Return a character-appropriate emoji based on the character ID."""
    if "momo" in char_id:
        return "🐰"  # bunny
    elif "tinku" in char_id:
        return "🧸"  # teddy bear
    elif "pihu" in char_id:
        return "☁️"  # cloud
    elif "golu" in char_id:
        return "🐘"  # elephant
    elif "mimi" in char_id:
        return "🐦"  # bird
    elif "ira" in char_id:
        return "🧑‍🚀"  # astronaut
    return "🌟"  # star (fallback)


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
    """Generate a unique, cute SVG character reference illustration for each character."""
    title = escape(character.name)
    role = escape(character.role)
    desc = escape(character.description)
    cid = character.id

    if "momo" in cid:
        return _svg_momo(title, role, desc)
    elif "tinku" in cid:
        return _svg_tinku(title, role, desc)
    elif "pihu" in cid:
        return _svg_pihu(title, role, desc)
    elif "golu" in cid:
        return _svg_golu(title, role, desc)
    elif "mimi" in cid:
        return _svg_mimi(title, role, desc)
    elif "ira" in cid:
        return _svg_ira(title, role, desc)
    return _svg_fallback(title, role, desc)


def _svg_base(title: str, role: str, desc: str, bg_start: str, bg_end: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="1280" viewBox="0 0 960 1280">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop stop-color="{bg_start}"/>
      <stop offset="1" stop-color="{bg_end}"/>
    </linearGradient>
  </defs>
  <rect width="960" height="1280" fill="url(#bg)"/>
  <rect x="64" y="64" width="832" height="1152" rx="44" fill="#ffffff" opacity="0.95"/>
  <text x="96" y="152" fill="#111827" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" font-size="56" font-weight="700">{title}</text>
  <text x="96" y="208" fill="#6b7280" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" font-size="28" font-weight="600">{role}</text>
  <foreignObject x="96" y="1100" width="768" height="100">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; font-size: 22px; line-height: 1.35; color: #374151;">{desc}</div>
  </foreignObject>
"""


def _svg_momo(title: str, role: str, desc: str) -> str:
    """Momo the Bunny — soft pink/white bunny with long floppy ears."""
    return f"""{_svg_base(title, role, desc, "#fce4ec", "#c2185b")}
  <!-- body -->
  <ellipse cx="480" cy="680" rx="160" ry="180" fill="#f8bbd0"/>
  <ellipse cx="480" cy="700" rx="110" ry="100" fill="#ffffff" opacity="0.6"/>
  <!-- head -->
  <circle cx="480" cy="380" r="150" fill="#f1c0c8"/>
  <!-- left ear -->
  <ellipse cx="360" cy="180" rx="40" ry="120" fill="#e8a0b0" transform="rotate(-15 360 180)"/>
  <ellipse cx="360" cy="180" rx="22" ry="90" fill="#f5d0d8" transform="rotate(-15 360 180)"/>
  <!-- right ear -->
  <ellipse cx="600" cy="180" rx="40" ry="120" fill="#e8a0b0" transform="rotate(15 600 180)"/>
  <ellipse cx="600" cy="180" rx="22" ry="90" fill="#f5d0d8" transform="rotate(15 600 180)"/>
  <!-- cheeks -->
  <circle cx="400" cy="420" r="28" fill="#f48fb1" opacity="0.4"/>
  <circle cx="560" cy="420" r="28" fill="#f48fb1" opacity="0.4"/>
  <!-- eyes -->
  <ellipse cx="420" cy="360" rx="22" ry="28" fill="#3e2723"/>
  <ellipse cx="540" cy="360" rx="22" ry="28" fill="#3e2723"/>
  <ellipse cx="414" cy="352" rx="8" ry="10" fill="#ffffff"/>
  <ellipse cx="534" cy="352" rx="8" ry="10" fill="#ffffff"/>
  <!-- nose -->
  <ellipse cx="480" cy="400" rx="12" ry="8" fill="#ec407a"/>
  <!-- mouth -->
  <path d="M460 415 Q480 435 500 415" fill="none" stroke="#3e2723" stroke-width="4" stroke-linecap="round"/>
  <!-- whiskers -->
  <line x1="360" y1="400" x2="420" y2="405" stroke="#9e9e9e" stroke-width="2" stroke-linecap="round"/>
  <line x1="360" y1="412" x2="420" y2="412" stroke="#9e9e9e" stroke-width="2" stroke-linecap="round"/>
  <line x1="600" y1="400" x2="540" y2="405" stroke="#9e9e9e" stroke-width="2" stroke-linecap="round"/>
  <line x1="600" y1="412" x2="540" y2="412" stroke="#9e9e9e" stroke-width="2" stroke-linecap="round"/>
  <!-- feet -->
  <ellipse cx="400" cy="860" rx="50" ry="30" fill="#f1c0c8"/>
  <ellipse cx="560" cy="860" rx="50" ry="30" fill="#f1c0c8"/>
  <!-- tail -->
  <circle cx="300" cy="760" r="25" fill="#ffffff"/>
  <text x="96" y="1070" fill="#111827" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" font-size="26" font-weight="700">&#11088; For Meta AI</text>
</svg>"""


def _svg_tinku(title: str, role: str, desc: str) -> str:
    """Tinku the Teddy — warm brown teddy bear with red bow."""
    return f"""{_svg_base(title, role, desc, "#efebe9", "#5d4037")}
  <!-- body -->
  <ellipse cx="480" cy="700" rx="150" ry="170" fill="#8d6e63"/>
  <ellipse cx="480" cy="720" rx="100" ry="90" fill="#d7ccc8" opacity="0.5"/>
  <!-- arms -->
  <ellipse cx="310" cy="640" rx="40" ry="80" fill="#8d6e63" transform="rotate(20 310 640)"/>
  <ellipse cx="650" cy="640" rx="40" ry="80" fill="#8d6e63" transform="rotate(-20 650 640)"/>
  <!-- head -->
  <circle cx="480" cy="370" r="140" fill="#8d6e63"/>
  <!-- ears -->
  <circle cx="370" cy="260" r="45" fill="#8d6e63"/>
  <circle cx="370" cy="260" r="28" fill="#a1887f"/>
  <circle cx="590" cy="260" r="45" fill="#8d6e63"/>
  <circle cx="590" cy="260" r="28" fill="#a1887f"/>
  <!-- red bow -->
  <polygon points="410,445 480,480 550,445 480,510" fill="#e53935"/>
  <circle cx="480" cy="478" r="10" fill="#c62828"/>
  <!-- eyes -->
  <circle cx="430" cy="350" r="20" fill="#3e2723"/>
  <circle cx="530" cy="350" r="20" fill="#3e2723"/>
  <circle cx="425" cy="344" r="7" fill="#ffffff"/>
  <circle cx="525" cy="344" r="7" fill="#ffffff"/>
  <!-- snout -->
  <ellipse cx="480" cy="390" rx="40" ry="28" fill="#d7ccc8"/>
  <ellipse cx="480" cy="385" rx="12" ry="8" fill="#3e2723"/>
  <!-- smile -->
  <path d="M458 405 Q480 425 502 405" fill="none" stroke="#3e2723" stroke-width="4" stroke-linecap="round"/>
  <!-- feet -->
  <ellipse cx="400" cy="870" rx="55" ry="35" fill="#8d6e63"/>
  <ellipse cx="560" cy="870" rx="55" ry="35" fill="#8d6e63"/>
  <ellipse cx="385" cy="865" rx="20" ry="14" fill="#a1887f"/>
  <ellipse cx="545" cy="865" rx="20" ry="14" fill="#a1887f"/>
  <text x="96" y="1070" fill="#111827" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" font-size="26" font-weight="700">&#11088; For Meta AI</text>
</svg>"""


def _svg_pihu(title: str, role: str, desc: str) -> str:
    """Pihu the Little Cloud — soft white/blue cloud with rainbow accent."""
    return f"""{_svg_base(title, role, desc, "#e3f2fd", "#1a237e")}
  <!-- cloud body using overlapping circles -->
  <circle cx="360" cy="520" r="100" fill="#ffffff" opacity="0.95"/>
  <circle cx="480" cy="480" r="130" fill="#ffffff" opacity="0.95"/>
  <circle cx="600" cy="520" r="100" fill="#ffffff" opacity="0.95"/>
  <circle cx="420" cy="550" r="90" fill="#e3f2fd" opacity="0.7"/>
  <circle cx="540" cy="550" r="90" fill="#e3f2fd" opacity="0.7"/>
  <ellipse cx="480" cy="590" rx="200" ry="60" fill="#ffffff" opacity="0.95"/>
  <!-- rainbow scarf -->
  <path d="M340 610 Q480 660 620 610" fill="none" stroke="#ff5252" stroke-width="8" stroke-linecap="round"/>
  <path d="M345 625 Q480 675 615 625" fill="none" stroke="#ffab40" stroke-width="8" stroke-linecap="round"/>
  <path d="M350 640 Q480 690 610 640" fill="none" stroke="#69f0ae" stroke-width="8" stroke-linecap="round"/>
  <path d="M355 655 Q480 705 605 655" fill="none" stroke="#40c4ff" stroke-width="8" stroke-linecap="round"/>
  <!-- face -->
  <circle cx="430" cy="500" r="18" fill="#37474f"/>
  <circle cx="530" cy="500" r="18" fill="#37474f"/>
  <circle cx="425" cy="494" r="6" fill="#ffffff"/>
  <circle cx="525" cy="494" r="6" fill="#ffffff"/>
  <ellipse cx="480" cy="530" rx="14" ry="10" fill="#ff8a80"/>
  <path d="M450 545 Q480 570 510 545" fill="none" stroke="#37474f" stroke-width="5" stroke-linecap="round"/>
  <!-- rosy cheeks -->
  <circle cx="400" cy="525" r="20" fill="#ff8a80" opacity="0.35"/>
  <circle cx="560" cy="525" r="20" fill="#ff8a80" opacity="0.35"/>
  <!-- raindrops -->
  <ellipse cx="300" cy="700" rx="8" ry="14" fill="#40c4ff" opacity="0.4"/>
  <ellipse cx="660" cy="720" rx="8" ry="14" fill="#40c4ff" opacity="0.4"/>
  <ellipse cx="320" cy="740" rx="6" ry="10" fill="#40c4ff" opacity="0.3"/>
  <ellipse cx="640" cy="760" rx="6" ry="10" fill="#40c4ff" opacity="0.3"/>
  <text x="96" y="1070" fill="#111827" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" font-size="26" font-weight="700">&#11088; For Meta AI</text>
</svg>"""


def _svg_golu(title: str, role: str, desc: str) -> str:
    """Golu the Baby Elephant — blue-gray with big ears, trunk, yellow scarf."""
    return f"""{_svg_base(title, role, desc, "#eceff1", "#37474f")}
  <!-- body -->
  <ellipse cx="480" cy="720" rx="170" ry="160" fill="#90a4ae"/>
  <ellipse cx="480" cy="740" rx="120" ry="90" fill="#b0bec5" opacity="0.5"/>
  <!-- yellow scarf -->
  <path d="M330 610 Q480 660 630 610" fill="none" stroke="#fdd835" stroke-width="18" stroke-linecap="round"/>
  <path d="M590 610 L620 680" stroke="#fdd835" stroke-width="18" stroke-linecap="round"/>
  <path d="M610 665 L635 635" stroke="#f9a825" stroke-width="8" stroke-linecap="round"/>
  <!-- legs -->
  <rect x="370" y="830" width="55" height="90" rx="27" fill="#90a4ae"/>
  <rect x="535" y="830" width="55" height="90" rx="27" fill="#90a4ae"/>
  <rect x="360" y="900" width="75" height="30" rx="15" fill="#78909c"/>
  <rect x="525" y="900" width="75" height="30" rx="15" fill="#78909c"/>
  <!-- head -->
  <circle cx="480" cy="400" r="140" fill="#90a4ae"/>
  <!-- big ears -->
  <ellipse cx="310" cy="410" rx="65" ry="90" fill="#90a4ae" transform="rotate(-10 310 410)"/>
  <ellipse cx="310" cy="410" rx="40" ry="60" fill="#b0bec5" transform="rotate(-10 310 410)"/>
  <ellipse cx="650" cy="410" rx="65" ry="90" fill="#90a4ae" transform="rotate(10 650 410)"/>
  <ellipse cx="650" cy="410" rx="40" ry="60" fill="#b0bec5" transform="rotate(10 650 410)"/>
  <!-- eyes -->
  <circle cx="430" cy="380" r="22" fill="#263238"/>
  <circle cx="530" cy="380" r="22" fill="#263238"/>
  <circle cx="424" cy="374" r="8" fill="#ffffff"/>
  <circle cx="524" cy="374" r="8" fill="#ffffff"/>
  <!-- trunk -->
  <path d="M480 420 Q490 450 475 490 Q470 500 478 510" fill="none" stroke="#78909c" stroke-width="28" stroke-linecap="round"/>
  <!-- smile -->
  <path d="M440 440 Q480 470 520 440" fill="none" stroke="#263238" stroke-width="4" stroke-linecap="round"/>
  <!-- red toy car badge -->
  <circle cx="580" cy="720" r="18" fill="#e53935"/>
  <rect x="572" y="714" width="16" height="8" rx="3" fill="#b71c1c"/>
  <circle cx="576" cy="726" r="4" fill="#ffcc02"/>
  <circle cx="588" cy="726" r="4" fill="#ffcc02"/>
  <!-- rosy cheeks -->
  <circle cx="400" cy="415" r="22" fill="#ef9a9a" opacity="0.35"/>
  <circle cx="560" cy="415" r="22" fill="#ef9a9a" opacity="0.35"/>
  <text x="96" y="1070" fill="#111827" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" font-size="26" font-weight="700">&#11088; For Meta AI</text>
</svg>"""


def _svg_mimi(title: str, role: str, desc: str) -> str:
    """Mimi the Bird — tiny round yellow bird with orange feet and teal bow."""
    return f"""{_svg_base(title, role, desc, "#fffde7", "#f57f17")}
  <!-- body -->
  <circle cx="480" cy="550" r="130" fill="#fdd835"/>
  <ellipse cx="480" cy="570" rx="100" ry="80" fill="#fff176" opacity="0.5"/>
  <!-- belly -->
  <ellipse cx="480" cy="600" rx="70" ry="60" fill="#fff9c4" opacity="0.7"/>
  <!-- teal bow -->
  <polygon points="430,440 380,400 380,480" fill="#26c6da"/>
  <polygon points="530,440 580,400 580,480" fill="#26c6da"/>
  <circle cx="480" cy="440" r="14" fill="#00acc1"/>
  <!-- head -->
  <circle cx="480" cy="420" r="90" fill="#fdd835"/>
  <!-- eyes -->
  <circle cx="445" cy="405" r="16" fill="#3e2723"/>
  <circle cx="515" cy="405" r="16" fill="#3e2723"/>
  <circle cx="441" cy="400" r="5" fill="#ffffff"/>
  <circle cx="511" cy="400" r="5" fill="#ffffff"/>
  <!-- beak -->
  <polygon points="480,415 460,435 500,435" fill="#ff6f00"/>
  <!-- wings -->
  <ellipse cx="330" cy="530" rx="50" ry="70" fill="#f9a825" transform="rotate(-15 330 530)"/>
  <ellipse cx="630" cy="530" rx="50" ry="70" fill="#f9a825" transform="rotate(15 630 530)"/>
  <ellipse cx="340" cy="525" rx="25" ry="40" fill="#ffee58" transform="rotate(-15 340 525)"/>
  <ellipse cx="620" cy="525" rx="25" ry="40" fill="#ffee58" transform="rotate(15 620 525)"/>
  <!-- rosy cheeks -->
  <circle cx="420" cy="435" r="16" fill="#ef9a9a" opacity="0.4"/>
  <circle cx="540" cy="435" r="16" fill="#ef9a9a" opacity="0.4"/>
  <!-- feet -->
  <line x1="440" y1="680" x2="440" y2="730" stroke="#ff6f00" stroke-width="6" stroke-linecap="round"/>
  <line x1="520" y1="680" x2="520" y2="730" stroke="#ff6f00" stroke-width="6" stroke-linecap="round"/>
  <line x1="440" y1="730" x2="420" y2="740" stroke="#ff6f00" stroke-width="4" stroke-linecap="round"/>
  <line x1="440" y1="730" x2="460" y2="740" stroke="#ff6f00" stroke-width="4" stroke-linecap="round"/>
  <line x1="520" y1="730" x2="500" y2="740" stroke="#ff6f00" stroke-width="4" stroke-linecap="round"/>
  <line x1="520" y1="730" x2="540" y2="740" stroke="#ff6f00" stroke-width="4" stroke-linecap="round"/>
  <!-- tail feathers -->
  <ellipse cx="280" cy="580" rx="18" ry="30" fill="#f9a825" transform="rotate(30 280 580)"/>
  <ellipse cx="270" cy="600" rx="14" ry="25" fill="#ffee58" transform="rotate(20 270 600)"/>
  <text x="96" y="1070" fill="#111827" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" font-size="26" font-weight="700">&#11088; For Meta AI</text>
</svg>"""


def _svg_ira(title: str, role: str, desc: str) -> str:
    """Commander Ira — detailed space suit illustration with helmet, mission patch, and amber visor."""
    return f"""{_svg_base(title, role, desc, "#0f172a", "#1e3a5f")}
  <!-- star field background inside card -->
  <circle cx="160" cy="160" r="2" fill="#ffffff" opacity="0.6"/>
  <circle cx="720" cy="120" r="1.5" fill="#ffffff" opacity="0.4"/>
  <circle cx="800" cy="300" r="1" fill="#ffffff" opacity="0.5"/>
  <circle cx="200" cy="900" r="1.5" fill="#ffffff" opacity="0.3"/>
  <circle cx="750" cy="850" r="2" fill="#ffffff" opacity="0.4"/>
  <circle cx="640" cy="200" r="1" fill="#ffffff" opacity="0.35"/>
  <circle cx="300" cy="1000" r="1.5" fill="#ffffff" opacity="0.25"/>
  <!-- body / torso -->
  <rect x="370" y="580" width="220" height="280" rx="40" fill="#e0e0e0"/>
  <rect x="380" y="595" width="200" height="120" rx="20" fill="#eeeeee" opacity="0.5"/>
  <!-- cobalt trim stripes on torso -->
  <rect x="370" y="740" width="220" height="8" rx="4" fill="#1a237e"/>
  <rect x="370" y="770" width="220" height="8" rx="4" fill="#1a237e"/>
  <!-- collar -->
  <rect x="390" y="555" width="180" height="40" rx="20" fill="#bdbdbd"/>
  <rect x="400" y="560" width="160" height="30" rx="15" fill="#9e9e9e"/>
  <!-- frost crystals on collar -->
  <line x1="410" y1="562" x2="415" y2="568" stroke="#e0f7fa" stroke-width="1.5" opacity="0.6"/>
  <line x1="550" y1="564" x2="545" y2="570" stroke="#e0f7fa" stroke-width="1.5" opacity="0.6"/>
  <line x1="480" y1="560" x2="483" y2="566" stroke="#e0f7fa" stroke-width="1" opacity="0.4"/>
  <!-- mission patch (triangular, red/gold on navy, seven-pointed star + orbits) -->
  <polygon points="380,630 420,630 400,672" fill="#d32f2f" stroke="#fdd835" stroke-width="2"/>
  <polygon points="388,640 412,640 400,662" fill="#1a237e"/>
  <!-- seven-pointed star (approximated with overlapping triangles) -->
  <polygon points="400,645 396,653 404,653" fill="#fdd835"/>
  <polygon points="396,650 404,650 400,658" fill="#fdd835"/>
  <!-- crossed orbits -->
  <ellipse cx="400" cy="652" rx="6" ry="2" fill="none" stroke="#fdd835" stroke-width="1" transform="rotate(-30 400 652)"/>
  <ellipse cx="400" cy="652" rx="6" ry="2" fill="none" stroke="#fdd835" stroke-width="1" transform="rotate(30 400 652)"/>
  <!-- left arm -->
  <rect x="300" y="590" width="70" height="240" rx="35" fill="#e0e0e0"/>
  <rect x="300" y="590" width="70" height="120" rx="35" fill="#eeeeee" opacity="0.4"/>
  <rect x="335" y="610" width="8" height="200" rx="4" fill="#1a237e"/>
  <!-- left shoulder light -->
  <rect x="295" y="585" width="16" height="30" rx="8" fill="#78909c"/>
  <circle cx="303" cy="600" r="5" fill="#fdd835"/>
  <circle cx="303" cy="600" r="3" fill="#ffffff" opacity="0.8"/>
  <!-- right arm -->
  <rect x="590" y="590" width="70" height="240" rx="35" fill="#e0e0e0"/>
  <rect x="590" y="590" width="70" height="120" rx="35" fill="#eeeeee" opacity="0.4"/>
  <rect x="617" y="610" width="8" height="200" rx="4" fill="#1a237e"/>
  <!-- gloved hands -->
  <rect x="315" y="820" width="40" height="50" rx="18" fill="#78909c"/>
  <line x1="325" y1="835" x2="325" y2="865" stroke="#607d8b" stroke-width="2" stroke-linecap="round"/>
  <line x1="335" y1="835" x2="335" y2="865" stroke="#607d8b" stroke-width="2" stroke-linecap="round"/>
  <line x1="345" y1="835" x2="345" y2="865" stroke="#607d8b" stroke-width="2" stroke-linecap="round"/>
  <rect x="605" y="820" width="40" height="50" rx="18" fill="#78909c"/>
  <line x1="615" y1="835" x2="615" y2="865" stroke="#607d8b" stroke-width="2" stroke-linecap="round"/>
  <line x1="625" y1="835" x2="625" y2="865" stroke="#607d8b" stroke-width="2" stroke-linecap="round"/>
  <line x1="635" y1="835" x2="635" y2="865" stroke="#607d8b" stroke-width="2" stroke-linecap="round"/>
  <!-- legs -->
  <rect x="395" y="840" width="65" height="180" rx="32" fill="#e0e0e0"/>
  <rect x="500" y="840" width="65" height="180" rx="32" fill="#e0e0e0"/>
  <rect x="410" y="850" width="8" height="160" rx="4" fill="#1a237e"/>
  <rect x="510" y="850" width="8" height="160" rx="4" fill="#1a237e"/>
  <!-- knee pads -->
  <rect x="390" y="940" width="70" height="40" rx="15" fill="#78909c"/>
  <rect x="500" y="940" width="70" height="40" rx="15" fill="#78909c"/>
  <!-- boots -->
  <rect x="385" y="1010" width="80" height="40" rx="20" fill="#78909c"/>
  <rect x="495" y="1010" width="80" height="40" rx="20" fill="#78909c"/>
  <rect x="380" y="1030" width="90" height="20" rx="10" fill="#607d8b"/>
  <rect x="490" y="1030" width="90" height="20" rx="10" fill="#607d8b"/>
  <!-- utility belt -->
  <rect x="370" y="810" width="220" height="30" rx="10" fill="#616161"/>
  <rect x="378" y="812" width="2" height="26" fill="#424242"/>
  <rect x="580" y="812" width="2" height="26" fill="#424242"/>
  <!-- silver pouches -->
  <rect x="420" y="812" width="28" height="30" rx="6" fill="#9e9e9e"/>
  <rect x="515" y="812" width="28" height="30" rx="6" fill="#9e9e9e"/>
  <line x1="434" y1="812" x2="434" y2="842" stroke="#757575" stroke-width="1.5"/>
  <line x1="529" y1="812" x2="529" y2="842" stroke="#757575" stroke-width="1.5"/>
  <!-- scuff marks -->
  <ellipse cx="400" cy="900" rx="12" ry="4" fill="#9e9e9e" opacity="0.4"/>
  <ellipse cx="560" cy="890" rx="10" ry="3" fill="#9e9e9e" opacity="0.35"/>
  <ellipse cx="330" cy="800" rx="8" ry="3" fill="#9e9e9e" opacity="0.3"/>
  <!-- helmet -->
  <circle cx="480" cy="370" r="130" fill="#e0e0e0"/>
  <circle cx="480" cy="370" r="120" fill="#eeeeee"/>
  <circle cx="480" cy="370" r="115" fill="#f5f5f5"/>
  <!-- helmet visor (amber, semi-reflective gradient effect) -->
  <ellipse cx="480" cy="370" rx="82" ry="90" fill="#ff8f00" opacity="0.35"/>
  <ellipse cx="475" cy="365" rx="80" ry="88" fill="#ffb300" opacity="0.15"/>
  <!-- visor reflection highlights -->
  <path d="M430 330 Q460 310 490 320" fill="none" stroke="#ffffff" stroke-width="6" opacity="0.25" stroke-linecap="round"/>
  <path d="M510 430 Q530 420 540 400" fill="none" stroke="#ffffff" stroke-width="4" opacity="0.15" stroke-linecap="round"/>
  <!-- warm brown eyes visible through visor -->
  <ellipse cx="445" cy="360" rx="12" ry="7" fill="#5d4037" opacity="0.7"/>
  <ellipse cx="515" cy="360" rx="12" ry="7" fill="#5d4037" opacity="0.7"/>
  <circle cx="442" cy="358" r="3" fill="#3e2723" opacity="0.5"/>
  <circle cx="512" cy="358" r="3" fill="#3e2723" opacity="0.5"/>
  <!-- breathing tube -->
  <path d="M540 380 Q560 385 550 410" fill="none" stroke="#78909c" stroke-width="10" stroke-linecap="round"/>
  <path d="M540 380 Q560 385 550 410" fill="none" stroke="#90a4ae" stroke-width="6" stroke-linecap="round"/>
  <!-- helmet LED light -->
  <rect x="435" y="255" width="12" height="18" rx="4" fill="#bdbdbd"/>
  <circle cx="441" cy="258" r="4" fill="#40c4ff"/>
  <circle cx="441" cy="258" r="2" fill="#ffffff" opacity="0.7"/>
  <!-- ice residue on visor edge -->
  <path d="M410 420 Q415 425 412 430" fill="none" stroke="#b3e5fc" stroke-width="2" opacity="0.4" stroke-linecap="round"/>
  <path d="M545 415 Q550 420 547 425" fill="none" stroke="#b3e5fc" stroke-width="2" opacity="0.35" stroke-linecap="round"/>
  <text x="96" y="1070" fill="#e0e0e0" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" font-size="26" font-weight="700">&#11088; For Meta AI</text>
</svg>"""


def _svg_fallback(title: str, role: str, desc: str) -> str:
    return _svg_base(title, role, desc, "#111827", "#312e81") + f"""
  <circle cx="480" cy="430" r="190" fill="#60a5fa"/>
  <circle cx="410" cy="394" r="26" fill="#111827"/>
  <circle cx="550" cy="394" r="26" fill="#111827"/>
  <circle cx="402" cy="386" r="8" fill="#ffffff"/>
  <circle cx="542" cy="386" r="8" fill="#ffffff"/>
  <path d="M405 505 Q480 565 555 505" fill="none" stroke="#111827" stroke-width="16" stroke-linecap="round"/>
  <rect x="310" y="635" width="340" height="310" rx="80" fill="#60a5fa"/>
  <rect x="346" y="680" width="268" height="54" rx="27" fill="#22d3ee"/>
  <circle cx="315" cy="470" r="74" fill="#60a5fa" opacity="0.92"/>
  <circle cx="645" cy="470" r="74" fill="#60a5fa" opacity="0.92"/>
  <text x="96" y="1070" fill="#111827" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif" font-size="26" font-weight="700">Consistency Notes</text>
</svg>"""


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
