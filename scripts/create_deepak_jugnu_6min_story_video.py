from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from content_pipeline.bots.audio import (
    generate_indian_voiceover,
    mix_storytelling_with_adaptive_music,
)
from cartoonize_story_video import _concat_segments, _duration_seconds, _mux_audio, _render_zoom_segment


OUTPUT_DIR = Path("output/youtube_assets/deepak_jugnu_next_story_6min")
SOURCE_IMAGE_DIR = Path("output/youtube_assets/deepak_jugnu_nvidia_cartoonized_continuity/images")
FINAL_VIDEO = OUTPUT_DIR / "Deepak_Aur_Jugnu_Next_6Min_Story.mp4"
FINAL_TARGET_SECONDS = 355.0
NARRATION_RAW = OUTPUT_DIR / "audio" / "narration_raw.mp3"
NARRATION_MIXED = OUTPUT_DIR / "audio" / "narration_mixed.mp3"
ROTATION_STATE = OUTPUT_DIR / ".story_rotation.json"

IMG_WIDE = SOURCE_IMAGE_DIR / "01_01_key6_walk_with_calf_cartoon_2k.png"
IMG_WALK = SOURCE_IMAGE_DIR / "02_02_key2_wide_path_cartoon_2k.png"
IMG_HAND = SOURCE_IMAGE_DIR / "03_03_key2_hand_hold_cartoon_2k.png"
IMG_HELP = SOURCE_IMAGE_DIR / "04_04_key6_calf_help_cartoon_2k.png"
IMG_DETAIL = SOURCE_IMAGE_DIR / "05_05_key6_walk_detail_cartoon_2k.png"
IMG_CLOSE = SOURCE_IMAGE_DIR / "06_06_key6_calf_close_cartoon_2k.png"


@dataclass(frozen=True)
class StoryVariant:
    name: str
    story_text: str
    sequence: list[tuple[str, Path, str]]


def _story_variants() -> list[StoryVariant]:
    return [
        StoryVariant(
            name="rainy-calf-rescue",
            story_text="""
The rain had just stopped, and the whole village felt fresh and quiet, as if the ground itself had taken a deep breath. Deepak sat beside his grandmother on the veranda, listening to the last drops fall from the mango leaves. The sky was turning blue again, but the path beyond the house was still muddy and soft. Deepak liked evenings like this because everything felt calm enough for stories.

Then he heard it. A small, trembling sound from the lane near the mango tree. It was not loud. It was not scary. It sounded more like a baby calling for help after getting lost. Deepak stood up right away. His grandmother listened too, and then she said the same thing any careful elder would say: something small and frightened was nearby, and it needed kindness before it needed answers.

Deepak followed the sound to the mango tree. There, standing under the wet leaves, was a little calf covered in mud. Its legs were thin, its coat was brown and white, and its eyes kept looking in every direction, as if it had forgotten where home was. Deepak did not rush toward it. He walked slowly so the calf would not panic. He held out one hand, crouched down, and spoke in a gentle voice. The calf blinked, stopped stepping backward, and finally stood still long enough for Deepak to see how tired it really was.

His grandmother came closer with a small bowl of water. She did not make a fuss. She simply placed the bowl on the ground and said the calf probably needed water, warmth, and one patient friend. Deepak agreed. He moved the bowl a little closer, then stepped back. The calf sniffed the air, took one careful sip, and then another. That tiny act felt important. Deepak could see that the calf was not stubborn or wild. It was only lost.

After a few minutes, the calf began looking past the house toward the fields. It turned its head again and again in the same direction, almost like it remembered something important but could not quite reach it. Deepak understood at once. The calf was searching for its mother. That thought changed everything. This was not just a muddy animal standing in the wrong place. This was a child trying to get home.

So Deepak went back to the kitchen and brought a small piece of jaggery. He offered it carefully. The calf hesitated, then accepted the sweet bite. That was the first time its breathing softened. Its shoulders loosened. Its eyes became less worried. Deepak smiled. His grandmother smiled too, because sometimes the smallest gift can turn fear into trust.

By then the village had filled with fireflies. They drifted through the lanes like tiny lanterns, yellow and gold, bright enough to make the wet walls glow. Deepak looked at them and felt as if they were pointing the way. He decided that if the calf could not find its family alone, then he would help it. His grandmother agreed, and together they began walking toward the fields at the edge of the village.

The path was narrow. On one side there were banana plants with heavy green leaves. On the other side, low mud banks held the rainwater in small shining pockets. Deepak walked slowly in front, and the calf followed in tiny uncertain steps. Every few moments Deepak would stop and talk softly so the calf would keep calm. He told it they were close, that the fields were not far, and that its mother was probably worried somewhere ahead. The calf seemed to understand more than a little, because it kept moving whenever Deepak spoke.

At the edge of the fields, his grandmother lifted her hand and pointed. In the dark green grass, a larger cow was walking in circles, clearly restless. She kept turning her head as if she had been searching for hours. Deepak did not need anyone to explain it. The mother was calling for her baby, and the baby had finally come within sight.

Deepak slowly turned the calf toward the field. For a second the little one froze, and then it saw the cow. In one quick motion it ran forward. The mother cow stopped, lowered her head, and touched the calf with such quiet tenderness that Deepak felt his own chest go warm. The calf pressed close to her side. The two of them stood together in the grass as if the whole village had been waiting for that exact moment.

Just then, the farmer from the nearby land came running over with a flashlight and muddy boots. Deepak expected a scolding, but the farmer only looked relieved. He thanked Deepak and his grandmother over and over. He said the calf had wandered off after the rain and he had been too worried to sit still. Deepak felt shy, the way children do when they have helped someone and suddenly get praised for it. He said the real guide had been the fireflies, not him. His grandmother laughed softly and told him that a kind heart always notices the path sooner than fear does.

The farmer invited them to sit under a small tin roof near the edge of the field. He brought warm milk, a little jaggery, and a dry cloth to wipe the mud from Deepak’s hands. The rain clouds moved apart while they rested. The night turned clearer. The fireflies kept glowing, and the village looked peaceful in a way that only happens after a problem has been solved kindly.

Deepak watched the calf stay close to its mother and thought about what had happened. He had not fought anyone. He had not done anything loud or dramatic. He had simply listened, walked carefully, and refused to leave a frightened little creature alone. His grandmother noticed the look on his face and asked what he was thinking. Deepak said, very honestly, that helping felt bigger when it was quiet.

His grandmother nodded. She told him that courage is not always about strong hands or fast feet. Sometimes courage is staying calm, moving slowly, and treating a lost creature like it matters. Deepak remembered that sentence. He knew he would remember it for a long time.

When they started home, the fireflies followed them for a little while as if they were still keeping watch. Deepak looked back once more at the field, at the mother cow, and at the calf now safe beside her. Then he looked up at the dark sky, where the stars had become visible again. He felt proud, but in a quiet way. It was the kind of pride that makes a child stand a little taller without wanting to shout.

At the veranda, Deepak sat down beside his grandmother and listened to the village night settle around them. The mud on his feet no longer mattered. What mattered was the memory of a frightened calf finding its mother and a whole evening turning gentle because someone chose patience first. Deepak smiled to himself and understood something simple and true: home is not just a place with walls and a roof. Home is the feeling that someone will notice when you are lost, and stay long enough to help you back.
""".strip(),
            sequence=[
                ("01_start", IMG_WIDE, "in"),
                ("02_find_calf", IMG_WALK, "out"),
                ("03_talk", IMG_HAND, "in"),
                ("04_guided", IMG_HELP, "out"),
                ("05_firefly_path", IMG_DETAIL, "in"),
                ("06_return", IMG_CLOSE, "out"),
            ],
        ),
        StoryVariant(
            name="bamboo-bridge-return",
            story_text="""
The morning had a silver shine after the rain, and Deepak woke up to the smell of wet earth and fresh grass. He and his grandmother walked toward the paddy edge with a small lunch bundle and a brass water cup, because the village always felt busiest after a storm. Deepak liked that time of day. Everything looked new, as if the world had been rinsed clean.

Near the narrow path by the field, they heard a soft cry. It came from the low side of the embankment where rainwater had gathered in a shallow stream. Deepak hurried closer and found a little brown-white calf standing still, its hooves sunk in mud and its body turned toward the water. The calf was not hurt, but it was frightened. It kept looking back and forth, unsure which way was safe.

Deepak did not pull or shout. He crouched down, spoke gently, and asked his grandmother to stay still so the calf could calm down. She noticed a few fallen banana stems nearby and told Deepak they could make a small path. Together they laid the stems across the wet patch like a narrow bridge. It was not a perfect bridge, but it was enough for a careful step and a brave heart.

The calf watched them for a long moment. Then Deepak held out the brass cup with a little water, and the calf took one sip, then another. Its ears relaxed. Its breathing slowed. Deepak felt the little victory in his chest, the quiet kind that does not ask to be praised.

As the sun climbed higher, the air filled with birdsong and the smell of leaves drying in the warm light. Deepak walked one step ahead, his grandmother walked beside him, and the calf followed the new path they had made. Every few steps Deepak pointed toward the fields and spoke softly, as if he were guiding a friend home from a place that had looked too big and too wet.

At the far edge of the paddy, a larger cow came into view. She had been waiting near a clump of tall grass, restless and alert, turning in circles as if the minutes had become too long. The moment the calf saw her, it rushed forward. The mother cow met it halfway, lowering her head with such tenderness that Deepak felt the scene quiet everything else around him.

The farmer arrived soon after with muddy boots and a very relieved face. He thanked Deepak and his grandmother for helping without frightening the calf. He said the baby had wandered off while the rain was still falling and every small delay had felt enormous. Deepak listened and thought about the banana-stem bridge. It had not been strong in the usual way. It had only been patient enough to help.

Before they went home, the farmer gave them ripe guava slices and tea in small steel cups. Deepak sat on a stone wall, looking out at the fields, and his grandmother told him that kindness often works like a bridge. It does not need to be loud. It only needs to reach the other side.

When they reached the veranda again, the village was bright and dry and busy in its own calm way. Deepak remembered the little calf stepping forward across the stems, and he knew the day had given him a lesson he would carry for a long time: when someone is scared, the right path is often the one made slowly, one careful step at a time.
""".strip(),
            sequence=[
                ("01_bridge_start", IMG_DETAIL, "out"),
                ("02_water_pause", IMG_HAND, "in"),
                ("03_bridge_build", IMG_WALK, "out"),
                ("04_calf_steps", IMG_HELP, "in"),
                ("05_mother_spot", IMG_CLOSE, "out"),
                ("06_home_tea", IMG_WIDE, "in"),
            ],
        ),
        StoryVariant(
            name="lantern-market-homecoming",
            story_text="""
By evening the village lane had turned gold with lantern light, and Deepak was helping his grandmother carry a basket of mangoes from the small market. The air smelled of cardamom, wet clay, and warm sugar. Deepak was tired in the happy way children are after a busy day, when the world feels full of tiny jobs and tiny surprises.

Near the temple corner, a faint sound broke the chatter of the road. It was a worried little call, soft enough that most people would have missed it. Deepak stopped at once. Under the banyan shade, a small calf stood beside a puddle, blinking fast and turning in circles. It had a patch of white on its forehead and mud up to its knees, and it looked very much like it had lost the thread back to home.

Deepak’s grandmother said not to rush. She always noticed the right thing first. So Deepak set the mango basket down, took a slow breath, and walked toward the calf with open hands. He picked a few fresh leaves from the roadside and held them low so the calf could smell them. Then he poured a little water into his palm and let the calf taste it one careful drop at a time.

The calf quieted. It stopped pulling away. Deepak could feel the moment it began to trust him, and that trust made his own steps calmer too. He glanced along the lane, and the lanterns seemed to line up like a gentle trail. Deepak decided to follow them. His grandmother smiled, because sometimes children notice the path in the most beautiful way.

They walked past the tea stall, past a row of bicycles, and past the temple wall where the evening bell was ringing. The calf moved in short, nervous steps, but it stayed near Deepak’s shoulder as if it had chosen him for the job. In the darkening field beyond the lane, a mother cow was waiting by the fence, calling softly with a low, steady voice.

The calf heard her and suddenly ran. The mother answered with a slow turn of the head and a tender nudge that made Deepak’s eyes sting a little. The farmer came running from the far side with a flashlight, first worried, then relieved, and finally laughing in the way adults laugh when a fear has turned into gratitude. He said the calf had wandered behind the grain cart while the market was busy.

Deepak, his grandmother, and the farmer sat for a few minutes under the tea stall roof. They drank warm tea and watched the lanterns sway. The farmer said the village always feels smaller when people help each other. Deepak liked that sentence. It sounded true in the same way the evening bell sounded true, steady and clear.

His grandmother added that every rescue leaves a mark, even when nobody claps for it. Deepak looked down at the mango basket and then at the muddy edge of the lane, and he imagined how many small turns a frightened animal has to make before it feels safe again. The thought stayed with him like a warm pebble in his pocket.

The farmer pointed to the grain cart and told Deepak that the calf had bolted when the market crowd became too loud after the rain. Deepak nodded and realized that being lost is often just being overwhelmed in the wrong moment. That made him even gentler in his own mind. He wanted to remember that feeling the next time someone needed patience instead of hurry.

Deepak asked his grandmother why the night felt so peaceful even after such a worry. She told him that when a village helps something small find home, the whole place breathes easier. The tea cooled slowly in their cups. The lanterns swayed. Even the road seemed to relax, as though it knew the hardest part was over.

The farmer laughed and said the calf would probably tell this story in its own way someday, if calves could tell stories at all. Deepak liked that idea and pictured a tiny version of the evening stored inside the animal like a soft memory. He imagined the puddle, the leaves, the lanterns, and the gentle hands that had not frightened it.

Before they stood up, Deepak took one more look at the temple lane. A few shoppers were still walking home, and the market noise was becoming softer every minute. He felt the strange happy calm that comes after doing something useful without planning to be praised. It made his shoulders relax and his steps feel lighter.

When they finally stood up to leave, the lanterns were still swaying above the road. Deepak carried the basket again, but it no longer felt heavy. He kept glancing toward the calf and its mother as they settled into the fence line together, one soft call and one quiet answer passing between them like a secret promise.

On the walk home, the market noise slowly faded behind them. The basket of mangoes felt lighter somehow. Deepak looked at the sky and then at his grandmother and understood that a good day does not need to be dramatic to be memorable. Sometimes it is only a small frightened calf, a few lanterns, and a quiet choice to be kind at exactly the right moment.
""".strip(),
            sequence=[
                ("01_market_start", IMG_CLOSE, "in"),
                ("02_lantern_path", IMG_WIDE, "out"),
                ("03_leaf_calm", IMG_HAND, "in"),
                ("04_temple_turn", IMG_DETAIL, "out"),
                ("05_mother_home", IMG_HELP, "in"),
                ("06_evening_return", IMG_WALK, "out"),
            ],
        ),
    ]


def _load_rotation_index(count: int) -> int:
    if count <= 0:
        raise ValueError("count must be positive")
    last_index = -1
    if ROTATION_STATE.exists():
        try:
            data = json.loads(ROTATION_STATE.read_text(encoding="utf-8"))
            last_index = int(data.get("last_variant_index", -1))
        except Exception:
            last_index = -1
    return (last_index + 1) % count


def _save_rotation_index(index: int) -> None:
    ROTATION_STATE.write_text(
        json.dumps({"last_variant_index": index}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _speed_adjust_video(input_path: Path, output_path: Path, speed_factor: float) -> None:
    speed_factor = max(1.0, float(speed_factor))
    if speed_factor <= 1.01:
        shutil.copy2(input_path, output_path)
        return
    temp_output = output_path.with_name(f"{output_path.stem}.speeding.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-filter_complex",
            f"[0:v]setpts=PTS/{speed_factor:.6f}[v];[0:a]atempo={speed_factor:.6f}[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
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
            "-movflags",
            "+faststart",
            str(temp_output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    temp_output.replace(output_path)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "audio").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "images").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "segments").mkdir(parents=True, exist_ok=True)

    variants = _story_variants()
    variant_index = _load_rotation_index(len(variants))
    variant = variants[variant_index]

    narration_voice = "en-IN-PrabhatNeural"
    generate_indian_voiceover(
        variant.story_text,
        NARRATION_RAW,
        voice=narration_voice,
        rate="+0%",
        pitch="+0Hz",
    )
    mix_storytelling_with_adaptive_music(NARRATION_RAW, variant.story_text, NARRATION_MIXED)
    narration_duration = _duration_seconds(NARRATION_MIXED)

    copied_images = []
    for index, (slug, source, zoom) in enumerate(variant.sequence, start=1):
        target = OUTPUT_DIR / "images" / f"{index:02d}_{slug}_cartoon_2k.png"
        shutil.copy2(source, target)
        copied_images.append({"source": str(source), "path": str(target), "zoom": zoom})

    segment_duration = narration_duration / len(copied_images)
    segment_paths: list[Path] = []
    for index, image in enumerate(copied_images, start=1):
        segment_path = OUTPUT_DIR / "segments" / f"segment_{index:02d}_{image['zoom']}.mp4"
        _render_zoom_segment(
            Path(image["path"]),
            segment_path,
            duration=segment_duration,
            zoom_mode=str(image["zoom"]),
        )
        segment_paths.append(segment_path)

    silent_video = OUTPUT_DIR / "Deepak_Aur_Jugnu_Next_6Min_silent.mp4"
    _concat_segments(segment_paths, silent_video)
    _mux_audio(silent_video, NARRATION_MIXED, FINAL_VIDEO)
    speed_factor = max(1.0, narration_duration / FINAL_TARGET_SECONDS)
    adjusted_video = OUTPUT_DIR / "Deepak_Aur_Jugnu_Next_6Min_Story_Final.mp4"
    _speed_adjust_video(FINAL_VIDEO, adjusted_video, speed_factor)
    adjusted_video.replace(FINAL_VIDEO)
    _save_rotation_index(variant_index)

    manifest = {
        "title": "Deepak Aur Jugnu - Next Story",
        "story_variant": variant.name,
        "story_text": variant.story_text,
        "narration_voice": narration_voice,
        "audio_raw": str(NARRATION_RAW),
        "audio_mixed": str(NARRATION_MIXED),
        "audio_duration_seconds": narration_duration,
        "final_target_seconds": FINAL_TARGET_SECONDS,
        "speed_factor_applied": speed_factor,
        "output_video": str(FINAL_VIDEO),
        "images": copied_images,
        "segments": [str(path) for path in segment_paths],
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
