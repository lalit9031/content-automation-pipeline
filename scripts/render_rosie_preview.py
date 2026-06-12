from __future__ import annotations

from dataclasses import replace
from math import pi, cos, sin
from pathlib import Path

from content_pipeline.bots.science_video_agent import (
    assemble_final_video,
    assemble_scene_clips,
    create_science_video_workspace,
    generate_narration_audio,
)
from content_pipeline.config import Settings
from content_pipeline.models import ScienceScene, ScienceStoryScript


def build_rosie_script() -> ScienceStoryScript:
    scenes = [
        ScienceScene(
            chapter="Morning Colors",
            chapter_index=1,
            scene_index=1,
            title="Rosie Wakes Up",
            narration_hi=(
                "Good morning! A little rabbit named Rosie wakes up in a sunny garden. "
                "She smiles and says, Today I will find colors, animals, and numbers."
            ),
            on_screen_text_hi="Good Morning, Rosie!",
            visual_prompt=(
                "A warm storybook illustration of a cute bunny named Rosie waking up near a cozy "
                "cottage in a bright spring garden. Soft watercolor textures, glowing morning light, "
                "flowers swaying gently, cheerful and child-friendly, rich color, magical but simple."
            ),
            duration_seconds=10,
        ),
        ScienceScene(
            chapter="Color Hunt",
            chapter_index=1,
            scene_index=2,
            title="The Colors Around Rosie",
            narration_hi=(
                "Rosie sees a red apple, a yellow duck, a blue sky, a green leaf, an orange carrot, "
                "and a purple flower. Rosie says the colors out loud with a happy voice."
            ),
            on_screen_text_hi="Red. Yellow. Blue. Green. Orange. Purple.",
            visual_prompt=(
                "Rosie the rabbit in a bright storybook meadow discovering a red apple, yellow duck, "
                "blue sky, green leaf, orange carrot, and purple flower. Gentle motion, colorful "
                "paper-cutout and watercolor style, cute and educational for little kids."
            ),
            duration_seconds=11,
        ),
        ScienceScene(
            chapter="Friendly Animals",
            chapter_index=2,
            scene_index=3,
            title="Rosie Meets Friends",
            narration_hi=(
                "Rosie meets a cat, a dog, a bird, and a fish. The cat says meow. The dog says woof. "
                "The bird says chirp. The fish swims in the pond. Rosie waves hello to all her friends."
            ),
            on_screen_text_hi="Cat. Dog. Bird. Fish.",
            visual_prompt=(
                "A playful storybook scene with Rosie the bunny greeting a smiling cat, dog, bird, "
                "and fish by a little pond. Bright but soft colors, rounded shapes, joyful child-safe "
                "expressions, watercolor children's book style."
            ),
            duration_seconds=11,
        ),
        ScienceScene(
            chapter="Counting Fun",
            chapter_index=3,
            scene_index=4,
            title="Count With Rosie",
            narration_hi=(
                "Rosie counts one apple, two ducks, three balloons, four leaves, five carrots, "
                "six flowers, seven stars, eight clouds, nine butterflies, and ten happy smiles."
            ),
            on_screen_text_hi="1 2 3 4 5 6 7 8 9 10",
            visual_prompt=(
                "A bright counting scene in a charming storybook meadow with Rosie the bunny and "
                "big colorful numbers one to ten floating softly around apples, ducks, balloons, "
                "leaves, carrots, flowers, stars, clouds, butterflies, and smiles. Warm, clear, "
                "simple, and visually engaging for preschool kids."
            ),
            duration_seconds=12,
        ),
        ScienceScene(
            chapter="Goodbye",
            chapter_index=4,
            scene_index=5,
            title="Rosie Says Goodbye",
            narration_hi=(
                "Rosie claps her paws and says, I can see colors. I can name animals. I can count. "
                "Learning is fun! Then Rosie waves goodbye and hops home as the sun sets."
            ),
            on_screen_text_hi="Learning is fun!",
            visual_prompt=(
                "A gentle bedtime ending in a storybook garden as Rosie the bunny waves goodbye near "
                "her cozy cottage at sunset. Golden light, drifting sparkles, flowers and trees moving "
                "softly, warm and emotional, a perfect closing scene for little children."
            ),
            duration_seconds=10,
        ),
    ]

    return ScienceStoryScript(
        title="Rosie's Rainbow Adventure",
        topic="Colors, animals, and counting",
        tagline="A gentle preschool storybook adventure for ages 4 to 6.",
        chapters=[
            "Morning Colors",
            "Color Hunt",
            "Friendly Animals",
            "Counting Fun",
            "Goodbye",
        ],
        scenes=scenes,
        intro_music_hint="light ukulele, bells, and soft piano",
        background_music_mood="cheerful, gentle, magical preschool storybook",
    )


def main() -> int:
    # Lightweight helper for local previews of the Rosie story pipeline.
    # This deliberately stays small so it can be useful as a scratchpad.
    script = build_rosie_script()
    settings = Settings.from_environment(Path.cwd())
    workspace = create_science_video_workspace(settings, replace(settings, output_dir=Path("output/rosie_preview")))
    narration = generate_narration_audio(script, workspace)
    assemble_scene_clips(script, workspace, narration)
    assemble_final_video(workspace, script)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
