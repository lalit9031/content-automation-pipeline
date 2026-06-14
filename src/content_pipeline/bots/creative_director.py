"""Creative Director Agent — a conversational AI that understands the full
content automation pipeline and orchestrates its tools to turn story concepts
into finished video, audio, and image assets.

Architecture
------------
    User chats naturally about a story concept
            │
            ▼
    CreativeDirector processes the message
            │
            ├── Conversational reply (suggestions, ideas, questions)
            └── Action dispatch (if the user asks to generate something)
                    │
                    ├── generate_image → ImageProvider
                    ├── generate_story_script → prompt.py / OpenAI
                    ├── generate_audio → generate_indian_voiceover
                    ├── generate_music → generate_layered_kids_instrumental
                    ├── generate_video → video.py / video_engine.py
                    └── generate_comic → pm_video_agents / pm_slide_router
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from content_pipeline.config import Settings
from content_pipeline.models import ContentPackage, LongFormVideoScript

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  AGENT SYSTEM PROMPT
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Creative Director Agent — a conversational AI assistant embedded in a powerful content automation pipeline. You understand every tool in the system and can orchestrate them to bring story concepts to life.

## Your Personality
- Warm, creative, and thoughtful — you're a story editor, not a robot
- Ask clarifying questions when the concept needs more definition
- Suggest creative directions, character arcs, visual styles, and narrative twists
- Speak with enthusiasm about the creative work

## Available Tools & Capabilities

### 1. 🎨 Image Generation
Generate cinematic, stylized images from text prompts.
- **Providers**: NVIDIA FLUX (default, free), OpenAI DALL-E, Gemini Imagen, Pollinations (free fallback)
- **Styles**: 3D Claymation/Pixar, Photorealistic, Flat Vector, Cinematic Anime
- **Sizes**: 1:1 (1080x1080), 16:9 (2560x1440), 9:16 (1080x1920)
- **When to use**: Character concept art, story backgrounds, thumbnail concepts, mood boards

### 2. 🎙️ Voice & Audio
Generate natural voiceovers and audio.
- **Edge TTS**: Free, supports English & Hindi, multiple voice presets (corporate, storyteller, toddler, etc.)
- **Gemini TTS**: Premium voices (Rasalgethi, Puck, Charon, Kore, Fenrir, Aoede) — 50/day budget
- **Voice Cloning**: Hugging Face Spaces or Voicebox (local desktop app)
- **When to use**: Narration voiceovers, character voices, dubbing

### 3. 🎵 Music Generation
Generate original background music and songs.
- **Instrumental tracks**: Layered kids instrumental, cinematic scores, story background music
- **Song generation**: DiffRhythm2 for full songs with lyrics (Hindi & English)
- **Moods**: Calm, happy, sad, suspense, magic, adventure, cinematic
- **When to use**: Background scores for stories, nursery rhymes, song videos

### 4. 📝 Story & Script Generation
Generate structured stories and video scripts.
- **Science stories**: 30-minute cinematic science documentaries (Hindi narration)
- **Story Studio**: Short story episodes (kids/adult) with scene-by-scene breakdowns
- **PM video scripts**: Educational project management content
- **Long-form scripts**: 3-5 minute YouTube explainers
- **When to use**: Any structured narrative content

### 5. 🎬 Video Assembly
Assemble images + audio into finished videos.
- **Landscape previews**: 1280x720 explainer videos with animated zooms
- **Long-form videos**: Multi-scene narrated videos with subtitles
- **2D animated videos**: KidsStudio Orchestrator pipeline (character sprites, backgrounds, lip-sync)
- **Comic book videos**: Panel-based visual narratives
- **When to use**: Final video output from image + audio assets

### 6. 🚀 Publishing
Upload finished content to social platforms.
- **YouTube**: Upload with policy checks, description, tags
- **LinkedIn**: Image posting with infographic templates
- **Instagram**: Reel publishing
- **When to use**: When finished content needs distribution

## Conversation Flow Guidelines

1. **Listen first**: When the user shares a concept, respond with enthusiasm and understanding before jumping to execution
2. **Explore**: Ask about tone, audience, visual style, and narrative arc
3. **Suggest**: Offer 2-3 creative directions the user might not have considered
4. **Offer to execute**: When the concept feels ready, ask if they'd like to generate something specific
5. **Be proactive**: If the user mentions a character like "Kabir Anand — The Myth-Keeper", suggest:
   - Character concept art
   - A logline / story bible expansion
   - The first monster or antagonist
   - A mood board or visual style reference

## Output Format Rules
- Keep responses conversational and warm
- If the user asks you to generate something (image, audio, story), say "I can do that!" and describe what tool you'll use
- When suggesting directions, use short bullet points or short paragraphs
- Never mention internal API details or provider names unless the user asks
- If you can't do something, say so honestly and offer alternatives
"""


# ---------------------------------------------------------------------------
#  HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from text (handles markdown code blocks)."""
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _key_pool(values: tuple[str, ...] | list[str], fallback: str = "") -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for v in values:
        t = str(v).strip()
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    f = fallback.strip()
    if not ordered and f:
        ordered.append(f)
    return ordered


# ---------------------------------------------------------------------------
#  ACTION TYPES
# ---------------------------------------------------------------------------

class ActionType(Enum):
    """Actions the Creative Director can dispatch."""
    CONVERSATION = "conversation"
    GENERATE_IMAGE = "generate_image"
    GENERATE_STORY = "generate_story"
    GENERATE_AUDIO = "generate_audio"
    GENERATE_MUSIC = "generate_music"
    GENERATE_VIDEO = "generate_video"
    SUGGEST_DIRECTIONS = "suggest_directions"
    ANALYZE_CONCEPT = "analyze_concept"


@dataclass
class Action:
    """An action returned by the agent after processing a message."""
    type: ActionType
    payload: dict[str, Any] = field(default_factory=dict)
    response: str = ""


@dataclass
class ConversationTurn:
    """A single turn in the conversation history."""
    role: str  # "user" | "assistant"
    content: str
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


# ---------------------------------------------------------------------------
#  CREATIVE DIRECTOR CORE
# ---------------------------------------------------------------------------

class CreativeDirector:
    """Conversational AI agent that understands the full content pipeline."""
    
    def __init__(
        self,
        settings: Settings,
        *,
        llm_provider: str = "openai",
        conversation_dir: Path | None = None,
    ) -> None:
        self.settings = settings
        self.llm_provider = llm_provider
        self.conversation_dir = conversation_dir or (settings.output_dir / ".creative_director")
        self.conversation_dir.mkdir(parents=True, exist_ok=True)
        
        # Conversation history
        self.history: list[ConversationTurn] = []
        self.conversation_id = f"cd_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Load any existing conversation
        self._load_history()
        
        # Cache for generated assets
        self.last_generated: dict[str, Any] = {}
    
    # -----------------------------------------------------------------------
    #  PUBLIC API
    # -----------------------------------------------------------------------
    
    def chat(self, message: str) -> Action:
        """Process a user message and return an action with response.
        
        The agent:
        1. Decides if this is a creative conversation or a generation request
        2. If conversation → returns CONVERSATION action with reply
        3. If generation → returns GENERATE_* action with payload
        4. If suggestion → returns SUGGEST_DIRECTIONS action
        """
        # Record user message
        self.history.append(ConversationTurn(role="user", content=message))
        
        # Build the prompt with full context
        prompt = self._build_prompt(message)
        
        # Get LLM response
        raw_response = self._call_llm(prompt)
        
        # Try to extract a structured action
        action = self._parse_action(raw_response, message)
        
        # Record assistant response
        self.history.append(ConversationTurn(role="assistant", content=action.response))
        self._save_history()
        
        return action
    
    def analyze_concept(self, concept: str) -> Action:
        """Deep analysis of a story concept — returns structured breakdown."""
        prompt = (
            f"Analyze this story concept deeply:\n\n{concept}\n\n"
            "Provide a structured analysis covering:\n"
            "1. Core premise and genre\n"
            "2. Main character archetype\n"
            "3. Thematic tension and stakes\n"
            "4. Visual style suggestions (color palette, era, mood)\n"
            "5. 3 possible directions to take the story\n"
            "6. What the first visual asset should be (character art, environment, etc.)\n\n"
            "Return your analysis in a warm, conversational style."
        )
        self.history.append(ConversationTurn(role="user", content=concept))
        response = self._call_llm(self._build_prompt(prompt))
        action = Action(
            type=ActionType.ANALYZE_CONCEPT,
            payload={"concept": concept},
            response=response,
        )
        self.history.append(ConversationTurn(role="assistant", content=response))
        self._save_history()
        return action
    
    def generate_image(self, prompt: str, style: str = "3D Claymation / Pixar", aspect_ratio: str = "16:9") -> Path | None:
        """Generate an image using the configured image provider."""
        from content_pipeline.bots.image import image_provider, ImageVariant
        
        variant_map = {
            "1:1": ImageVariant("1:1", 1080, 1080, "creative_director_image_square"),
            "16:9": ImageVariant("16:9", 2560, 1440, "creative_director_image_landscape"),
            "9:16": ImageVariant("9:16", 1080, 1920, "creative_director_image_portrait"),
        }
        variant = variant_map.get(aspect_ratio, variant_map["16:9"])
        
        # Build a cinematic prompt
        full_prompt = (
            f"{prompt}\n\n"
            f"Style: {style}. Masterpiece, 8k resolution, cinematic lighting, "
            "clean composition, no text, no logos, no watermarks."
        )
        
        try:
            provider = image_provider(self.settings)
            image_bytes = provider.create(full_prompt, variant)
            
            # Save to disk
            output_dir = self.conversation_dir / "images"
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            slug = re.sub(r"[^a-zA-Z0-9]+", "_", prompt[:40].strip().lower()).strip("_")[:30]
            image_path = output_dir / f"{timestamp}_{slug}{provider.extension}"
            image_path.write_bytes(image_bytes)
            
            self.last_generated["image"] = str(image_path)
            return image_path
        except Exception as exc:
            log.error(f"Image generation failed: {exc}")
            return None
    
    def generate_story_script(
        self,
        concept: str,
        *,
        target_minutes: int = 5,
        language: str = "english",
        audience: str = "general",
    ) -> dict[str, Any] | None:
        """Generate a structured story script from a concept."""
        from content_pipeline.bots.prompt import (
            generate_long_form_video_script,
            MockPromptProvider,
            ContentPackage,
        )
        
        # Create a temporary content package to use the long-form generator
        # Or use the science story agent for longer form
        try:
            from content_pipeline.bots.science_story_agent import (
                generate_science_story_script,
                save_script_to_disk,
            )
            
            script = generate_science_story_script(
                self.settings,
                topic=concept[:100],
                target_minutes=min(target_minutes, 30),
            )
            
            paths = save_script_to_disk(script, str(self.settings.output_dir))
            self.last_generated["story"] = {
                "title": script.title,
                "scenes": len(script.scenes),
                "duration_seconds": script.duration_seconds,
                "paths": paths,
            }
            return {
                "title": script.title,
                "topic": script.topic,
                "scenes": [scene.as_dict() for scene in script.scenes],
                "duration_seconds": script.duration_seconds,
                "paths": paths,
            }
        except Exception as exc:
            log.warning(f"Science story generation failed, trying long-form: {exc}")
        
        # Fallback: use the long-form video script generator
        try:
            mock_package = ContentPackage.from_dict({
                "date": date.today().isoformat(),
                "topic": concept[:80],
                "image_prompt": concept[:200],
                "linkedin_infographic": {
                    "headline": concept[:58],
                    "subtitle": concept[:70],
                    "left_panel": {"title": "The Story", "points": ["Beginning", "Middle", "End"]},
                    "right_panel": {"title": "The Themes", "points": ["Conflict", "Growth", "Resolution"]},
                    "takeaway_title": "Key Lesson",
                    "takeaway_points": ["The journey matters"],
                    "workflow": ["Idea", "Draft", "Refine", "Share"],
                    "discussion_prompt": "What do you think?",
                },
                "video_script": {
                    "hook": f"What if {concept[:60]}?",
                    "points": [concept[:80]],
                    "cta": "Share your thoughts below",
                },
                "linkedin_caption": concept[:200],
                "hashtags": ["#Storytelling", "#CreativeWriting"],
                "seo_title": concept[:60],
                "seo_description": concept[:160],
            })
            script = generate_long_form_video_script(mock_package, self.settings, target_minutes=min(target_minutes, 5))
            self.last_generated["story"] = {
                "title": script.title,
                "scenes": len(script.scenes),
                "duration_seconds": script.duration_seconds,
            }
            return {
                "title": script.title,
                "scenes": [scene.as_dict() for scene in script.scenes],
                "duration_seconds": script.duration_seconds,
            }
        except Exception as exc:
            log.error(f"Story generation failed: {exc}")
            return None
    
    def generate_audio(
        self,
        text: str,
        voice: str = "en-IN-PrabhatNeural",
        *,
        output_path: Path | None = None,
    ) -> Path | None:
        """Generate voiceover audio from text."""
        from content_pipeline.bots.audio import generate_indian_voiceover
        
        if output_path is None:
            output_dir = self.conversation_dir / "audio"
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"{timestamp}_voiceover.mp3"
        
        try:
            result = generate_indian_voiceover(text, output_path, voice=voice)
            self.last_generated["audio"] = str(result)
            return result
        except Exception as exc:
            log.error(f"Audio generation failed: {exc}")
            return None
    
    def generate_music(
        self,
        *,
        mood: str = "calm",
        duration_seconds: int = 30,
        style_description: str = "",
        output_path: Path | None = None,
    ) -> Path | None:
        """Generate background music."""
        from content_pipeline.bots.audio import generate_layered_kids_instrumental
        
        if output_path is None:
            output_dir = self.conversation_dir / "music"
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = output_dir / f"{timestamp}_music.mp3"
        
        try:
            result = generate_layered_kids_instrumental(
                output_path,
                duration_seconds=duration_seconds,
                style_description=style_description,
            )
            self.last_generated["music"] = str(result)
            return result
        except Exception as exc:
            log.error(f"Music generation failed: {exc}")
            return None
    
    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.history.clear()
        self._save_history()
    
    def export_conversation(self) -> str:
        """Export the conversation as markdown."""
        lines = ["# Creative Director — Conversation Log", ""]
        for turn in self.history:
            role = "**You**" if turn.role == "user" else "**Creative Director**"
            lines.append(f"{role} ({turn.timestamp.split('T')[0]}):")
            lines.append(turn.content)
            lines.append("")
        return "\n".join(lines)
    
    # -----------------------------------------------------------------------
    #  INTERNAL METHODS
    # -----------------------------------------------------------------------
    
    def _build_prompt(self, message: str) -> str:
        """Build the full prompt with system instructions and conversation history."""
        parts = [SYSTEM_PROMPT]
        
        # Add context about the current project state
        parts.append("\n\n## Current Project Context\n")
        output_dir = self.settings.output_dir
        daily_root = output_dir / "daily"
        if daily_root.exists():
            day_count = len([d for d in daily_root.iterdir() if d.is_dir()])
            parts.append(f"- Daily runs completed: {day_count}")
            latest = sorted(d.name for d in daily_root.iterdir() if d.is_dir())
            if latest:
                parts.append(f"- Latest run: {latest[-1]}")
        
        # Add recent history (last 6 turns)
        recent = self.history[-6:] if len(self.history) > 6 else self.history
        if recent:
            parts.append("\n\n## Recent Conversation\n")
            for turn in recent:
                label = "User" if turn.role == "user" else "Assistant"
                content_preview = turn.content[:200] + ("..." if len(turn.content) > 200 else "")
                parts.append(f"{label}: {content_preview}")
        
        # Add current message
        parts.append(f"\n\n## Current User Message\n{message}")
        
        # Add last generated assets context
        if self.last_generated:
            parts.append("\n\n## Last Generated Assets\n")
            for key, value in self.last_generated.items():
                parts.append(f"- {key}: {value}")
        
        return "\n".join(parts)
    
    def _call_llm(self, prompt: str) -> str:
        """Call the LLM and return the response text."""
        # Try providers in order: openai, nvidia, gemini, local
        providers: list[tuple[str, Callable[[str], str | None]]] = [
            ("openai", self._call_openai),
            ("nvidia", self._call_nvidia),
            ("gemini", self._call_gemini),
            ("local", self._call_local),
        ]
        
        # If a specific provider is configured, try that first
        if self.llm_provider == "openai":
            providers = [("openai", self._call_openai)] + [
                p for p in providers if p[0] != "openai"
            ]
        
        last_error: Exception | None = None
        for name, func in providers:
            try:
                result = func(prompt)
                if result:
                    return result
            except Exception as exc:
                last_error = exc
                log.warning(f"LLM provider '{name}' failed: {exc}")
                continue
        
        # Ultimate fallback: return a canned response
        log.error(f"All LLM providers failed. Last error: {last_error}")
        return (
            "I'm sorry, I'm having trouble connecting to my creative engine right now. "
            "Please check your API keys (OPENAI_API_KEY or GEMINI_API_KEY) in the .env file "
            "and try again. I'd love to help with your story concept once we're connected!"
        )
    
    def _call_openai(self, prompt: str) -> str | None:
        """Call OpenAI API."""
        keys = _key_pool(self.settings.openai_api_keys, self.settings.openai_api_key)
        if not keys:
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        
        for key in keys:
            try:
                client = OpenAI(api_key=key)
                response = client.responses.create(
                    model=self.settings.openai_model,
                    instructions=SYSTEM_PROMPT[:500],
                    input=prompt,
                )
                return response.output_text
            except Exception as exc:
                log.warning(f"OpenAI key failed: {exc}")
                continue
        return None
    
    def _call_nvidia(self, prompt: str) -> str | None:
        """Call NVIDIA NIM API."""
        keys = _key_pool(self.settings.nvidia_api_keys, self.settings.nvidia_api_key)
        if not keys:
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        
        model = (
            os.getenv("NVIDIA_TEXT_MODEL", "")
            or self.settings.nvidia_nim_model
            or "microsoft/phi-4-mini-instruct"
        )
        for key in keys:
            try:
                client = OpenAI(api_key=key, base_url="https://integrate.api.nvidia.com/v1")
                completion = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    max_tokens=2048,
                    stream=False,
                )
                return str(completion.choices[0].message.content or "")
            except Exception as exc:
                log.warning(f"NVIDIA key failed: {exc}")
                continue
        return None
    
    def _call_gemini(self, prompt: str) -> str | None:
        """Call Gemini API."""
        keys = _key_pool(self.settings.gemini_api_keys, self.settings.gemini_api_key)
        if not keys:
            return None
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return None
        
        for key in keys:
            try:
                client = genai.Client(api_key=key)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"{SYSTEM_PROMPT}\n\n{prompt}",
                )
                return response.text
            except Exception as exc:
                log.warning(f"Gemini key failed: {exc}")
                continue
        return None
    
    def _call_local(self, prompt: str) -> str | None:
        """Call local LLM (Ollama, LM Studio)."""
        try:
            from openai import OpenAI
        except ImportError:
            return None
        try:
            client = OpenAI(api_key="local", base_url=self.settings.local_llm_url)
            completion = client.chat.completions.create(
                model=self.settings.local_llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2048,
                stream=False,
            )
            return str(completion.choices[0].message.content or "")
        except Exception as exc:
            log.warning(f"Local LLM failed: {exc}")
            return None
    
    def _parse_action(self, response: str, user_message: str) -> Action:
        """Parse the LLM response to determine if it's a generation request."""
        # Default: just a conversation response
        return Action(
            type=ActionType.CONVERSATION,
            payload={"message": user_message},
            response=response,
        )
    
    def _load_history(self) -> None:
        """Load conversation history from disk."""
        history_path = self.conversation_dir / "conversation_history.json"
        if not history_path.exists():
            return
        try:
            data = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self.history = [
                    ConversationTurn(
                        role=item.get("role", "assistant"),
                        content=item.get("content", ""),
                        timestamp=item.get("timestamp", ""),
                    )
                    for item in data
                ]
        except Exception:
            pass
    
    def _save_history(self) -> None:
        """Save conversation history to disk."""
        history_path = self.conversation_dir / "conversation_history.json"
        try:
            data = [
                {
                    "role": turn.role,
                    "content": turn.content,
                    "timestamp": turn.timestamp,
                }
                for turn in self.history
            ]
            history_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning(f"Failed to save conversation history: {exc}")
