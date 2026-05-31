from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil
from typing import Any

from content_pipeline.bots.pm_video_templates import (
    PMVideoTemplate,
    select_pm_video_template_for_role,
)


@dataclass(frozen=True)
class SlideRoute:
    route_id: str
    role: str
    agent_name: str
    provider: str
    provider_slot: str
    slide_start: int
    slide_end: int
    template_roles: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["template_roles"] = list(self.template_roles)
        return data


@dataclass(frozen=True)
class SlidePlanItem:
    index: int
    title: str
    on_screen_text: str
    narration: str
    role: str
    agent_name: str
    provider: str
    provider_slot: str
    template_id: str
    template_name: str
    template_layout: str
    image_prompt: str
    api_key_family: str
    api_key_slot: str
    max_dimension: int
    max_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SlidePlan:
    topic: str
    day: str
    aspect: str
    total_slides: int
    routes: list[SlideRoute]
    slides: list[SlidePlanItem]

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "day": self.day,
            "aspect": self.aspect,
            "total_slides": self.total_slides,
            "routes": [route.as_dict() for route in self.routes],
            "slides": [slide.as_dict() for slide in self.slides],
        }


def build_slide_plan(
    topic: str,
    day: str,
    aspect: str,
    total_slides: int,
    template_mode: str,
    max_dimension: int,
    max_bytes: int,
    openai_key_count: int = 4,
    gemini_key_count: int = 4,
) -> SlidePlan:
    routes = _routes_for(aspect, total_slides)
    beat_rows = _beats_for(topic, aspect, total_slides)
    slides: list[SlidePlanItem] = []
    for index, beat in enumerate(beat_rows, start=1):
        route = _route_for_index(routes, index)
        template = select_pm_video_template_for_role(
            topic=topic,
            day=day,
            role=route.role,
            template_mode=template_mode,
            variant_index=index,
        )
        slides.append(
            SlidePlanItem(
                index=index,
                title=beat["title"],
                on_screen_text=beat["on_screen_text"],
                narration=beat["narration"],
                role=route.role,
                agent_name=route.agent_name,
                provider=route.provider,
                provider_slot=route.provider_slot,
                template_id=template.template_id,
                template_name=template.name,
                template_layout=template.layout,
                image_prompt=_image_prompt(topic, beat, route.role, template),
                api_key_family=route.provider,
                api_key_slot=_api_key_slot(route.provider, index, openai_key_count, gemini_key_count),
                max_dimension=max_dimension,
                max_bytes=max_bytes,
            )
        )
    return SlidePlan(
        topic=topic,
        day=day,
        aspect=aspect,
        total_slides=total_slides,
        routes=routes,
        slides=slides,
    )


def _routes_for(aspect: str, total_slides: int) -> list[SlideRoute]:
    if aspect == "shorts":
        roles = [
            ("hero", "Gemini Hero Agent", "gemini", "primary"),
            ("workflow", "Gemini Workflow Agent", "gemini", "secondary"),
            ("cta", "ChatGPT CTA Agent", "openai", "primary"),
        ]
    else:
        roles = [
            ("hero", "Gemini Hero Agent", "gemini", "primary"),
            ("workflow", "Gemini Workflow Agent", "gemini", "secondary"),
            ("analysis", "ChatGPT Analysis Agent", "openai", "primary"),
            ("cta", "ChatGPT Reference Agent", "openai", "backup"),
        ]
    spans = _split_spans(total_slides, len(roles))
    routes: list[SlideRoute] = []
    cursor = 1
    for index, (role, agent_name, provider, provider_slot) in enumerate(roles, start=1):
        count = spans[index - 1]
        start = cursor
        end = cursor + count - 1
        cursor = end + 1
        routes.append(
            SlideRoute(
                route_id=f"{role}_{index:02d}",
                role=role,
                agent_name=agent_name,
                provider=provider,
                provider_slot=provider_slot,
                slide_start=start,
                slide_end=end,
                template_roles=_template_roles_for(role),
            )
        )
    return routes


def _split_spans(total_slides: int, route_count: int) -> list[int]:
    base = total_slides // route_count
    remainder = total_slides % route_count
    return [base + (1 if index < remainder else 0) for index in range(route_count)]


def _route_for_index(routes: list[SlideRoute], slide_index: int) -> SlideRoute:
    for route in routes:
        if route.slide_start <= slide_index <= route.slide_end:
            return route
    return routes[-1]


def _beats_for(topic: str, aspect: str, total_slides: int) -> list[dict[str, str]]:
    if aspect == "shorts":
        base = [
            ("Hook", "Start strong", f"Today we turn {topic} into a practical PM playbook."),
            ("Context", "Why it matters", "This matters because teams need clarity without more admin."),
            ("Workflow", "Capture -> Draft -> Validate", "A simple loop helps AI support PM work safely."),
            ("Action", "Use the right prompt", "Ask AI for notes, action items, risks, and missing details."),
            ("Control", "Human review stays on", "AI prepares the work, but the project manager approves the outcome."),
            ("Example", "Jira and actions", "Keep decisions connected back to your delivery system of record."),
            ("Risk", "Check for gaps", "Use AI to surface dependencies, blockers, and unclear ownership."),
            ("Status", "Draft, then verify", "Draft updates are useful only after dates, scope, and commitments are checked."),
            ("Recap", "Simple formula", "Capture, draft, validate, communicate. That is the PM AI loop."),
            ("CTA", "Engage next", "Subscribe, ask questions, and suggest the next topic."),
        ]
    else:
        base = [
            ("Opening Hook", "The PM AI question", f"Today we unpack {topic} with a practical delivery lens."),
            ("Promise", "What you will learn", "You will see a workflow for using AI without losing human judgement."),
            ("Why Now", "More output, same time", "PMs need leverage because meetings, updates, and follow-ups never stop."),
            ("Capture", "Start with input", "Collect notes, risks, blockers, decisions, and open questions in one place."),
            ("Draft", "Generate useful first drafts", "Use AI for action lists, summaries, status updates, and backlog refinement."),
            ("Validate", "Check facts and ownership", "Human review must confirm dates, owners, dependencies, and scope."),
            ("Communicate", "Make the message clear", "Share only the verified version with the right audience."),
            ("Workflow", "Capture -> Draft -> Validate -> Communicate", "This loop keeps AI useful and accountable."),
            ("Examples", "Jira, PMO, stakeholder updates", "Apply the loop across boards, reporting, governance, and planning."),
            ("Risk", "What can fail", "Let AI reveal missed dependencies, privacy issues, and weak commitments."),
            ("Analysis", "Look for patterns", "Use AI to compare trends, surface repeated blockers, and spot weak signals."),
            ("Board", "Architecture of the workflow", "A clean system of record matters more than a noisy chat history."),
            ("Checklist", "What to keep consistent", "Use one tone, one process, and one human owner for every decision."),
            ("Comparison", "AI vs. manual process", "AI should reduce friction, not replace accountability."),
            ("Governance", "Keep control visible", "Protect privacy, approvals, and audit trails from the start."),
            ("Example 2", "Planning meeting output", "Turn a planning conversation into a cleaner delivery snapshot."),
            ("Example 3", "Executive update output", "Turn raw notes into a concise executive update."),
            ("Lesson", "Ask better questions", "The prompt quality matters more than the model hype."),
            ("Recap", "What to remember", "AI prepares. The PM decides. The team delivers."),
            ("CTA", "Next step", "Ask for the next topic, or suggest a full course."),
            ("Closing", "Stay connected", "Like, subscribe, and keep building with practical PM AI."),
            ("Appendix", "Decision log", "Keep decisions, owners, and follow-ups visible."),
            ("Appendix 2", "Risk register", "Track likely issues, impact, and mitigations."),
            ("Appendix 3", "Stakeholder map", "Know who needs what, when, and why."),
            ("Appendix 4", "Execution map", "Connect the narrative back to the delivery system."),
            ("Appendix 5", "Retro prompt", "Use AI to learn what worked and what to improve."),
            ("Appendix 6", "Governance checklist", "Verify policy, privacy, and review gates."),
            ("Appendix 7", "Template card", "Use a repeatable visual family for clarity."),
            ("Appendix 8", "Workflow card", "Show the process in a clean visual sequence."),
            ("Appendix 9", "Dashboard card", "Expose signal, not noise."),
            ("CTA Panel", "Invite action", "Comment, share, and request the next topic."),
            ("Final Summary", "One-line recap", "AI prepares. PM verifies. Delivery stays human."),
            ("References", "Evidence and notes", "Keep a record of the prompts, sources, and decisions used in the episode."),
            ("End Card", "Finish cleanly", "Use a calm closing frame so the last message lands without clutter."),
            ("Final CTA", "Like and subscribe", "If this helped, like the video and subscribe for more practical PM AI."),
        ]
    return [dict(title=title, on_screen_text=screen, narration=narration) for title, screen, narration in base[:total_slides]]


def _template_roles_for(role: str) -> tuple[str, ...]:
    if role == "hero":
        return ("podcast_cover", "stats_wall")
    if role == "workflow":
        return ("worksheet_grid", "workshop_notes")
    if role == "analysis":
        return ("stats_wall", "edu_infographic")
    return ("lesson_board", "podcast_cover", "workshop_notes")


def _image_prompt(topic: str, beat: dict[str, str], role: str, template: PMVideoTemplate) -> str:
    headline = _headline_for(topic, beat, role)
    hook = _hook_for(beat, role)
    concepts = _concepts_for(topic, beat)
    concept_text = "\n".join(f"- {concept}" for concept in concepts)
    
    # Premium 3D aesthetic parameters based on our highest-quality generated reference
    base_guardrails = (
        "No watermarks, no logos, no cluttered real-world screenshots, no generic stock-photo look. "
        "16:9 widescreen aspect ratio, ultra-detailed, cinematic quality. "
        "Style: Premium 3D character illustration with warm, expressive characters, friendly and approachable. "
        "Shapes and curves are beautifully rounded, smooth modern tech surfaces with tactile glassmorphism textures. "
        "Color Palette: Soft pastel purple and cyan highlights, subtle orange/gold glow, deep blue-grey background studio environment. "
        "Lighting: Soft volumetric studio lighting, gentle depth of field, subtle glowing particles, dramatic contrast. "
        "Absolutely no large readable text inside the image. Reserve a clean typography-safe area for text overlays."
    )
    
    if role == "cta":
        return (
            "Premium final course engagement slide, cinematic 3D character illustration. A warm, friendly robotic AI assistant companion "
            "with glowing yellow eyes floats in a high-contrast futuristic workspace next to a large glowing thumbs-up, subscribe play icon, "
            "and notification bell icon. Tactile glass cards with subtle orange and cyan glow. Dark blue grid studio background, "
            "professional final course slide for AI training. "
            f"Topic: {topic}\n"
            f'Renderer-only headline: "NEXT STEP: ENGAGE WITH THE COURSE!"\n'
            f'Renderer-only hook: "Ask questions, suggest topics, and stay part of the community."\n'
            f"Use the visual language of {template.style_line}. "
            f"{base_guardrails}"
        )
    if role == "workflow":
        return (
            "Premium process workflow slide, cinematic 3D character illustration. A friendly professional software manager or developer sits at "
            "a sleek minimalist glass desk, looking with an inspired smile at a floating, semi-transparent holographic process workflow dashboard. "
            "The dashboard displays glowing rounded flowchart nodes and clean process cards. A cute little robotic AI companion floats nearby. "
            "Cyan and pastel purple highlights, tactile glassmorphism elements.\n\n"
            f"Topic: {topic}\n"
            f'Renderer-only headline: "{headline}"\n'
            f'Renderer-only hook: "{hook}"\n'
            "Show large cinematic metaphors representing these process concepts:\n"
            f"{concept_text}\n"
            f"Use the visual language of {template.style_line}. "
            f"{base_guardrails}"
        )
    if role == "analysis":
        return (
            "Premium analytical learning scene, cinematic 3D character illustration. A professional project leader standing at a glowing high-tech "
            "shared conference table, inspecting a beautiful floating 3D analytical hologram showing rising growth arrows, glowing trend lines, "
            "and rounded data metrics. A small friendly robot companion sits on the table, pointing at a glowing visual checklist. "
            "Soft purple and cyan volumetric lights, glassmorphism dashboard highlights.\n\n"
            f"Topic: {topic}\n"
            f'Renderer-only headline: "{headline}"\n'
            f'Renderer-only hook: "{hook}"\n'
            "Show large cinematic metaphors representing these analytical insights:\n"
            f"{concept_text}\n"
            f"Use the visual language of {template.style_line}. "
            f"{base_guardrails}"
        )
    return (
        "Hero scene, bold YouTube learning video cover, cinematic 3D character illustration of a software developer "
        "sitting at a sleek minimalist desk in a futuristic workspace, looking with an inspired smile at a massive floating holographic "
        "dashboard displaying glowing rounded UI cards, flowchart nodes, and clean tech blocks. A friendly robotic AI companion floats beside "
        "the desk. Soft pastel purple and cyan highlights, gentle depth of field, warm volumetric lighting.\n\n"
        f"Topic: {topic}\n"
        f'Renderer-only headline: "{headline}"\n'
        f'Renderer-only hook: "{hook}"\n'
        "Show large cinematic metaphors representing these key concepts:\n"
        f"{concept_text}\n"
        f"Use the visual language of {template.style_line}. "
        f"{base_guardrails}"
    )


def _headline_for(topic: str, beat: dict[str, str], role: str) -> str:
    if role == "hero":
        return _short_title(topic).upper()
    if role == "cta":
        return "NEXT STEP: ENGAGE WITH THE COURSE!"
    return beat["on_screen_text"][:68]


def _hook_for(beat: dict[str, str], role: str) -> str:
    if role == "hero":
        return beat["on_screen_text"]
    if role == "cta":
        return "Ask questions, suggest topics, and stay part of the community."
    return beat["title"]


def _short_title(topic: str) -> str:
    title = topic.split(":", 1)[0].strip()
    if len(title) <= 42:
        return title
    words = title.split()
    shortened: list[str] = []
    for word in words:
        if len(" ".join(shortened + [word])) > 42:
            break
        shortened.append(word)
    return " ".join(shortened) or title[:42].strip()


def _concepts_for(topic: str, beat: dict[str, str]) -> tuple[str, str, str]:
    haystack = f"{topic} {beat['title']} {beat['on_screen_text']}".lower()
    if any(term in haystack for term in ("cycle time", "metric", "metrics")):
        return (
            "Cycle Time represented by a futuristic precision clock",
            "Escaped Defects represented by a glowing software bug breaking through a wall",
            "Delivery Confidence represented by a shield with a rising trend graph",
        )
    if any(term in haystack for term in ("jira", "workflow", "capture", "draft", "validate")):
        return (
            "Capture represented by meeting notes flowing into a luminous AI node",
            "Draft represented by clean action cards and backlog items",
            "Validate represented by a human approval gate and verified owner badges",
        )
    if any(term in haystack for term in ("risk", "governance", "policy", "audit")):
        return (
            "Risk visibility represented by a radar and dependency web",
            "Governance represented by a policy shield and approval checkpoint",
            "Human review represented by a PM decision gate",
        )
    if any(term in haystack for term in ("sprint", "retro", "planning", "safe", "agile")):
        return (
            "Sprint flow represented by a glowing agile board",
            "Dependency mapping represented by connected delivery nodes",
            "Team confidence represented by a shield and progress arc",
        )
    return (
        "Risk visibility represented by a glowing radar",
        "Flow speed represented by a clean delivery pipeline",
        "Human review represented by a PM approval checkpoint",
    )


def _api_key_slot(provider: str, index: int, openai_key_count: int, gemini_key_count: int) -> str:
    if provider == "gemini":
        count = max(1, gemini_key_count)
        slot = ((index - 1) % count) + 1
        return f"gemini_api_key_{slot}"
    count = max(1, openai_key_count)
    slot = ((index - 1) % count) + 1
    return f"openai_api_key_{slot}"
