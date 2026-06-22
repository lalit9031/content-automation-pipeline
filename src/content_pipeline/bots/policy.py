from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any


POLICY_REVIEWED_ON = date(2026, 5, 28)
POLICY_MAX_AGE_DAYS = 30
POLICY_SOURCES = [
    {
        "name": "YouTube made for kids guidance",
        "url": "https://support.google.com/youtube/answer/9528076",
    },
    {
        "name": "YouTube altered or synthetic content disclosure",
        "url": "https://support.google.com/youtube/answer/14328491",
    },
    {
        "name": "YouTube monetization policies",
        "url": "https://support.google.com/youtube/answer/1311392",
    },
    {
        "name": "OpenAI text-to-speech AI voice disclosure",
        "url": "https://developers.openai.com/api/docs/guides/text-to-speech",
    },
    {
        "name": "OpenAI Sora video guardrails and restrictions",
        "url": "https://developers.openai.com/api/docs/guides/video-generation",
    },
]


@dataclass(frozen=True)
class PublicationDeclarations:
    original_or_licensed_story: bool = False
    original_or_licensed_music: bool = False
    ai_audio_disclosed: bool = False
    ai_visuals_disclosed: bool = False
    fictional_or_consented_likenesses: bool = False
    no_face_reference_supplied_to_video_api: bool = False
    made_for_kids_selected: bool = False
    no_copyrighted_characters_or_style_copy: bool = False
    human_final_review: bool = False


def review_publication(
    title: str,
    video_file: str,
    declarations: PublicationDeclarations,
    checked_on: date | None = None,
) -> dict[str, Any]:
    checked_on = checked_on or date.today()
    path = Path(video_file)
    video_sha256 = _sha256(path) if path.is_file() else None
    freshness_cutoff = POLICY_REVIEWED_ON + timedelta(days=POLICY_MAX_AGE_DAYS)
    checks = [
        _check("final_video_exists", video_sha256 is not None, "The final reviewed MP4 exists and can be fingerprinted."),
        _check("story_rights", declarations.original_or_licensed_story, "Story/script is original or properly licensed."),
        _check("music_rights", declarations.original_or_licensed_music, "Music and sound effects are original or licensed for YouTube use."),
        _check("ai_voice_disclosure", declarations.ai_audio_disclosed, "Description states that narration is AI-generated."),
        _check("ai_visual_disclosure", declarations.ai_visuals_disclosed, "Description states that visuals are AI-assisted/generated."),
        _check("likeness_rights", declarations.fictional_or_consented_likenesses, "Characters are fictionalized or all relevant likeness permissions are recorded."),
        _check(
            "sora_face_input_restriction",
            declarations.no_face_reference_supplied_to_video_api,
            "No image containing a real human face is sent as Sora input reference.",
        ),
        _check("made_for_kids", declarations.made_for_kids_selected, "Kids story is configured as Made for Kids."),
        _check(
            "copyrighted_assets",
            declarations.no_copyrighted_characters_or_style_copy,
            "No copyrighted characters, copyrighted music, or direct studio-style copying is requested.",
        ),
        _check("human_approval", declarations.human_final_review, "A human reviewed the final render and upload metadata."),
        _check(
            "policy_freshness",
            checked_on <= freshness_cutoff,
            f"Policy sources must be rechecked after {freshness_cutoff.isoformat()}.",
        ),
    ]
    blockers = [check["id"] for check in checks if not check["passed"]]
    return {
        "title": title,
        "video_file": video_file,
        "video_sha256": video_sha256,
        "checked_on": checked_on.isoformat(),
        "policy_sources_reviewed_on": POLICY_REVIEWED_ON.isoformat(),
        "status": "approved_for_upload" if not blockers else "blocked",
        "blockers": blockers,
        "checks": checks,
        "sources": POLICY_SOURCES,
    }


def assert_upload_approved(report: dict[str, Any]) -> None:
    if report.get("status") != "approved_for_upload" or report.get("blockers"):
        blockers = ", ".join(report.get("blockers", [])) or "missing approval report"
        raise RuntimeError(f"YouTube upload blocked by publication policy review: {blockers}")


def _check(identifier: str, passed: bool, requirement: str) -> dict[str, Any]:
    return {"id": identifier, "passed": passed, "requirement": requirement}


def video_sha256(path: Path) -> str:
    return _sha256(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
