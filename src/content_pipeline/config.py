from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    output_dir: Path
    mode: str = "mock"
    prompt_provider: str = "mock"
    image_provider: str = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    imagen_model: str = "imagen-4.0-generate-001"
    publish_linkedin: bool = False
    linkedin_member_urn: str = ""

    @classmethod
    def from_environment(cls, project_dir: Path | None = None) -> "Settings":
        project_dir = project_dir or Path.cwd()
        _load_dotenv(project_dir / ".env")
        output_dir = Path(os.getenv("CONTENT_OUTPUT_DIR", "output"))
        if not output_dir.is_absolute():
            output_dir = project_dir / output_dir
        return cls(
            output_dir=output_dir,
            mode=os.getenv("PIPELINE_MODE", "mock").strip().lower(),
            prompt_provider=os.getenv("PROMPT_PROVIDER", "mock").strip().lower(),
            image_provider=os.getenv("IMAGE_PROVIDER", "mock").strip().lower(),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", ""),
            gcp_project_id=os.getenv("GCP_PROJECT_ID", ""),
            gcp_location=os.getenv("GCP_LOCATION", "us-central1"),
            imagen_model=os.getenv("IMAGEN_MODEL", "imagen-4.0-generate-001"),
            publish_linkedin=_as_bool(os.getenv("PUBLISH_LINKEDIN", "false")),
            linkedin_member_urn=os.getenv("LINKEDIN_MEMBER_URN", ""),
        )


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
