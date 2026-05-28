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
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_redirect_uri: str = "http://localhost:8080/callback"
    linkedin_access_token: str = ""
    linkedin_member_urn: str = ""
    canva_client_id: str = ""
    canva_client_secret: str = ""
    canva_redirect_uri: str = "http://127.0.0.1:8080/callback"
    canva_refresh_token: str = ""
    canva_brand_template_id: str = ""
    motion_provider: str = "openai_sora"
    motion_model: str = "sora-2"
    luma_api_key: str = ""
    luma_image_model: str = "photon-1"
    luma_video_model: str = "ray-2"
    gemini_api_key: str = ""
    gemini_video_model: str = "veo-3.0-generate-preview"
    gemini_video_poll_seconds: int = 10
    youtube_client_secrets_file: str = ""
    youtube_token_file: str = ""
    instagram_access_token: str = ""
    instagram_user_id: str = ""
    instagram_client_id: str = ""
    instagram_client_secret: str = ""
    dotenv_path: Path | None = None

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
            linkedin_client_id=os.getenv("LINKEDIN_CLIENT_ID", ""),
            linkedin_client_secret=os.getenv("LINKEDIN_CLIENT_SECRET", ""),
            linkedin_redirect_uri=os.getenv(
                "LINKEDIN_REDIRECT_URI", "http://localhost:8080/callback"
            ),
            linkedin_access_token=os.getenv("LINKEDIN_ACCESS_TOKEN", ""),
            linkedin_member_urn=os.getenv("LINKEDIN_MEMBER_URN", ""),
            canva_client_id=os.getenv("CANVA_CLIENT_ID", ""),
            canva_client_secret=os.getenv("CANVA_CLIENT_SECRET", ""),
            canva_redirect_uri=os.getenv(
                "CANVA_REDIRECT_URI", "http://127.0.0.1:8080/callback"
            ),
            canva_refresh_token=os.getenv("CANVA_REFRESH_TOKEN", ""),
            canva_brand_template_id=os.getenv("CANVA_BRAND_TEMPLATE_ID", ""),
            motion_provider=os.getenv("MOTION_PROVIDER", "openai_sora").strip().lower(),
            motion_model=os.getenv("MOTION_MODEL", "sora-2"),
            luma_api_key=os.getenv("LUMAAI_API_KEY", ""),
            luma_image_model=os.getenv("LUMA_IMAGE_MODEL", "photon-1"),
            luma_video_model=os.getenv("LUMA_VIDEO_MODEL", "ray-2"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", ""),
            gemini_video_model=os.getenv("GEMINI_VIDEO_MODEL", "veo-3.0-generate-preview"),
            gemini_video_poll_seconds=int(os.getenv("GEMINI_VIDEO_POLL_SECONDS", "10")),
            youtube_client_secrets_file=os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", ""),
            youtube_token_file=os.getenv("YOUTUBE_TOKEN_FILE", ""),
            instagram_access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
            instagram_user_id=os.getenv("INSTAGRAM_USER_ID", ""),
            instagram_client_id=os.getenv("INSTAGRAM_CLIENT_ID", ""),
            instagram_client_secret=os.getenv("INSTAGRAM_CLIENT_SECRET", ""),
            dotenv_path=project_dir / ".env",
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
